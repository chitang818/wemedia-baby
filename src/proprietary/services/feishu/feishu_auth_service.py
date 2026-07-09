"""
飞书授权服务
文件路径：src/proprietary/services/feishu/feishu_auth_service.py
功能：飞书 OAuth 授权、Token 加密存储与自动续期

授权流程（飞书自建应用 - 网页应用身份）：
1. 用户点击授权 → 生成授权 URL（带 app_id、redirect_uri、state、scope）
2. 用户在浏览器中完成授权 → 飞书回调 redirect_uri，携带 code
3. 本地 HTTP 服务接收回调 → 用 code 换取 access_token + refresh_token
4. Token 加密保存到本地 keyring

注意：此实现使用飞书「获取 user_access_token」接口，
文档：https://open.feishu.cn/document/server-docs/authentication-management/access-token/access_token
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple
from urllib.parse import urlencode, urlparse, parse_qs

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

FEISHU_OPEN_API_BASE = "https://open.feishu.cn/open-apis"

# 飞书授权相关 endpoint
AUTHORIZE_URL = f"{FEISHU_OPEN_API_BASE}/authen/v1/index"
ACCESS_TOKEN_URL = f"{FEISHU_OPEN_API_BASE}/authen/v1/access_token"
REFRESH_TOKEN_URL = f"{FEISHU_OPEN_API_BASE}/authen/v1/refresh_access_token"
USER_INFO_URL = f"{FEISHU_OPEN_API_BASE}/authen/v1/user_info"

# 本地回调端口范围（从低到高尝试，找到可用端口）
CALLBACK_PORT_START = 9527
CALLBACK_PORT_END = 9547

# 默认申请的权限范围（最小权限原则：只申请表格读取）
DEFAULT_SCOPE = "sheets:spreadsheet:readonly"

# Token 提前刷新的时间（秒）：在 token 过期前这么久就刷新
REFRESH_BEFORE_EXPIRE_SECONDS = 300

# keyring 中存储的 key 名
KEYRING_SERVICE = "媒小宝-飞书"
KEYRING_ACCESS_TOKEN = "feishu_access_token"
KEYRING_REFRESH_TOKEN = "feishu_refresh_token"
KEYRING_TOKEN_EXPIRES_AT = "feishu_token_expires_at"
KEYRING_USER_OPEN_ID = "feishu_user_open_id"
KEYRING_USER_NAME = "feishu_user_name"
KEYRING_USER_AVATAR = "feishu_user_avatar"


@dataclass
class FeishuUserInfo:
    """飞书用户信息"""
    open_id: str = ""
    user_id: str = ""
    name: str = ""
    avatar_url: str = ""
    email: str = ""
    mobile: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "FeishuUserInfo":
        return cls(
            open_id=data.get("open_id", "") or "",
            user_id=data.get("user_id", "") or "",
            name=data.get("name", "") or "",
            avatar_url=data.get("avatar_url", "") or "",
            email=data.get("email", "") or "",
            mobile=data.get("mobile", "") or "",
        )


class FeishuAuthService:
    """飞书授权服务（单例模式）

    使用飞书自建应用的网页授权能力，获取 user_access_token。
    Token 加密存储在系统 keyring 中，使用 EncryptionManager 进行加解密。
    """

    _instance: Optional["FeishuAuthService"] = None
    _instance_lock: Optional[asyncio.Lock] = None

    def __init__(self):
        self._token_lock = asyncio.Lock()
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None  # access_token 过期时间
        self._user_info: Optional[FeishuUserInfo] = None
        self._app_id: str = ""
        self._app_secret: str = ""
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "FeishuAuthService":
        """获取单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_app_config(self) -> bool:
        """加载应用凭证"""
        if self._app_id and self._app_secret:
            return True
        try:
            from .feishu_config import FeishuConfig
            cfg = FeishuConfig.load()
            self._app_id = cfg.app_id
            self._app_secret = cfg.app_secret
            return cfg.is_app_configured
        except Exception as e:
            logger.error("加载飞书应用配置失败: %s", e)
            return False

    def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._http_session

    async def close(self):
        """关闭资源"""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

    # ---------- Token 持久化 ----------

    def _load_tokens_from_storage(self) -> bool:
        """从 keyring 加载 Token"""
        try:
            import keyring
            from src.infrastructure.common.security.encryption import EncryptionManager

            access_enc = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCESS_TOKEN)
            refresh_enc = keyring.get_password(KEYRING_SERVICE, KEYRING_REFRESH_TOKEN)
            expires_enc = keyring.get_password(KEYRING_SERVICE, KEYRING_TOKEN_EXPIRES_AT)
            open_id_enc = keyring.get_password(KEYRING_SERVICE, KEYRING_USER_OPEN_ID)

            if not access_enc or not refresh_enc:
                return False

            self._access_token = EncryptionManager.decrypt_data(
                access_enc.encode()
            ).decode("utf-8")
            self._refresh_token = EncryptionManager.decrypt_data(
                refresh_enc.encode()
            ).decode("utf-8")

            if expires_enc:
                expires_str = EncryptionManager.decrypt_data(
                    expires_enc.encode()
                ).decode("utf-8")
                try:
                    self._expires_at = datetime.fromisoformat(expires_str)
                except (ValueError, TypeError):
                    self._expires_at = None

            if open_id_enc:
                open_id = EncryptionManager.decrypt_data(open_id_enc.encode()).decode("utf-8")
                
                name_enc = keyring.get_password(KEYRING_SERVICE, KEYRING_USER_NAME)
                name = EncryptionManager.decrypt_data(name_enc.encode()).decode("utf-8") if name_enc else ""
                
                avatar_enc = keyring.get_password(KEYRING_SERVICE, KEYRING_USER_AVATAR)
                avatar = EncryptionManager.decrypt_data(avatar_enc.encode()).decode("utf-8") if avatar_enc else ""
                
                self._user_info = FeishuUserInfo(open_id=open_id, name=name, avatar_url=avatar)

            return bool(self._access_token and self._refresh_token)
        except Exception as e:
            logger.debug("从 keyring 加载飞书 Token 失败: %s", e)
            return False

    def _save_tokens_to_storage(self) -> bool:
        """将 Token 加密保存到 keyring"""
        try:
            import keyring
            from src.infrastructure.common.security.encryption import EncryptionManager

            if self._access_token:
                keyring.set_password(
                    KEYRING_SERVICE,
                    KEYRING_ACCESS_TOKEN,
                    EncryptionManager.encrypt_data(
                        self._access_token.encode("utf-8")
                    ).decode("utf-8"),
                )
            if self._refresh_token:
                keyring.set_password(
                    KEYRING_SERVICE,
                    KEYRING_REFRESH_TOKEN,
                    EncryptionManager.encrypt_data(
                        self._refresh_token.encode("utf-8")
                    ).decode("utf-8"),
                )
            if self._expires_at:
                keyring.set_password(
                    KEYRING_SERVICE,
                    KEYRING_TOKEN_EXPIRES_AT,
                    EncryptionManager.encrypt_data(
                        self._expires_at.isoformat().encode("utf-8")
                    ).decode("utf-8"),
                )
            if self._user_info and self._user_info.open_id:
                keyring.set_password(
                    KEYRING_SERVICE,
                    KEYRING_USER_OPEN_ID,
                    EncryptionManager.encrypt_data(self._user_info.open_id.encode("utf-8")).decode("utf-8"),
                )
                if self._user_info.name:
                    keyring.set_password(
                        KEYRING_SERVICE,
                        KEYRING_USER_NAME,
                        EncryptionManager.encrypt_data(self._user_info.name.encode("utf-8")).decode("utf-8"),
                    )
                if self._user_info.avatar_url:
                    keyring.set_password(
                        KEYRING_SERVICE,
                        KEYRING_USER_AVATAR,
                        EncryptionManager.encrypt_data(self._user_info.avatar_url.encode("utf-8")).decode("utf-8"),
                    )
            return True
        except Exception as e:
            logger.error("保存飞书 Token 到 keyring 失败: %s", e, exc_info=True)
            return False

    def _clear_tokens_from_storage(self) -> bool:
        """清除 keyring 中的 Token"""
        try:
            import keyring
            for key in [
                KEYRING_ACCESS_TOKEN,
                KEYRING_REFRESH_TOKEN,
                KEYRING_TOKEN_EXPIRES_AT,
                KEYRING_USER_OPEN_ID,
                KEYRING_USER_NAME,
                KEYRING_USER_AVATAR,
            ]:
                try:
                    keyring.delete_password(KEYRING_SERVICE, key)
                except Exception:
                    pass
            return True
        except Exception:
            return False

    # ---------- 授权状态查询 ----------

    def is_app_configured(self) -> bool:
        """应用凭证是否已配置"""
        return self._load_app_config()

    async def is_authorized(self, verify: bool = False) -> bool:
        """检查是否已授权

        Args:
            verify: 是否调用接口校验 Token 有效性（慢但准确）
        """
        if not self._load_app_config():
            return False

        if not self._loaded:
            self._load_tokens_from_storage()
            self._loaded = True

        if not self._access_token or not self._refresh_token:
            return False

        if self._expires_at and self._expires_at > datetime.now():
            if not verify:
                return True

        try:
            token = await self.get_access_token()
            if not token:
                return False
            if verify:
                user_info = await self.fetch_user_info()
                return user_info is not None
            return True
        except Exception as e:
            logger.debug("检查飞书授权状态失败: %s", e)
            return False

    def get_user_info(self) -> Optional[FeishuUserInfo]:
        """获取当前用户信息（内存缓存，可能不完整）"""
        if not self._loaded:
            self._load_tokens_from_storage()
            self._loaded = True
        return self._user_info

    # ---------- 授权流程 ----------

    async def initiate_auth(
        self,
        scope: str = DEFAULT_SCOPE,
        preferred_port: Optional[int] = None,
    ) -> Tuple[str, str, int]:
        """发起授权，返回 (授权URL, state, 本地回调端口)

        Args:
            scope: 申请的权限范围
            preferred_port: 优先使用的回调端口

        Returns:
            (auth_url, state, port)
        """
        if not self._load_app_config():
            raise RuntimeError("飞书应用未配置，请先在配置中设置 app_id 和 app_secret")

        state = secrets.token_urlsafe(16)
        port = preferred_port or CALLBACK_PORT_START

        redirect_uri = f"http://127.0.0.1:{port}/callback"

        params = {
            "app_id": self._app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": scope,
        }
        auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"

        return auth_url, state, port

    async def _start_callback_server(
        self, port: int, expected_state: str, timeout: int = 300
    ) -> Optional[str]:
        """启动本地回调服务器，等待授权码

        Args:
            port: 监听端口
            expected_state: 预期的 state 值
            timeout: 超时时间（秒）

        Returns:
            授权码 code，超时返回 None
        """
        code_result: Optional[str] = None
        result_event = asyncio.Event()

        async def _callback_handler(request: web.Request) -> web.Response:
            nonlocal code_result
            try:
                code = request.query.get("code", "")
                state = request.query.get("state", "")

                if state != expected_state:
                    return web.Response(
                        text="授权失败：state 不匹配，请重新发起授权。",
                        content_type="text/html",
                        charset="utf-8",
                        status=400,
                    )

                if not code:
                    error = request.query.get("error", "未知错误")
                    return web.Response(
                        text=f"授权失败：{error}",
                        content_type="text/html",
                        charset="utf-8",
                        status=400,
                    )

                code_result = code
                result_event.set()

                html = """
                <html><head><meta charset="utf-8"><title>授权成功</title>
                <style>
                    body { display: flex; align-items: center; justify-content: center;
                           height: 100vh; margin: 0; background: #f5f7fa; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
                    .card { background: white; padding: 48px 64px; border-radius: 12px;
                            box-shadow: 0 4px 24px rgba(0,0,0,0.08); text-align: center; }
                    .icon { font-size: 48px; margin-bottom: 16px; }
                    h2 { margin: 0 0 8px 0; color: #1f2329; }
                    p { margin: 0; color: #646a73; }
                </style></head>
                <body><div class="card">
                    <div class="icon">✅</div>
                    <h2>授权成功</h2>
                    <p>飞书账号已成功授权，您可以关闭此页面返回软件。</p>
                </div></body></html>
                """
                return web.Response(text=html, content_type="text/html", charset="utf-8")
            except Exception as e:
                logger.error("回调处理异常: %s", e)
                return web.Response(status=500)

        app = web.Application()
        app.router.add_get("/callback", _callback_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)

        try:
            await site.start()
            logger.info("飞书回调服务器已启动，端口: %d", port)

            try:
                await asyncio.wait_for(result_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("飞书授权超时（%d秒）", timeout)
                return None

            return code_result
        finally:
            try:
                await runner.cleanup()
            except Exception:
                pass

    async def start_auth_flow(
        self,
        scope: str = DEFAULT_SCOPE,
        open_browser: bool = True,
        expected_state: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """启动完整授权流程

        在端口范围内尝试启动本地回调服务器，
        打开浏览器让用户授权，等待回调，获取并保存 Token。

        Args:
            scope: 权限范围
            open_browser: 是否自动打开浏览器

        Returns:
            (是否成功, 状态描述)
        """
        if not self._load_app_config():
            return False, "飞书应用未配置，请先联系管理员配置 app_id 和 app_secret"

        auth_url = ""
        state = expected_state or ""
        port = 0
        server_task = None

        for try_port in range(CALLBACK_PORT_START, CALLBACK_PORT_END + 1):
            try:
                auth_url, generated_state, port = await self.initiate_auth(scope, try_port)
                if not state:
                    state = generated_state
                break
            except Exception:
                continue

        if not auth_url:
            return False, "无法启动本地授权服务，请检查端口占用情况"

        server_task = asyncio.create_task(
            self._start_callback_server(port, state)
        )

        try:
            if open_browser:
                try:
                    webbrowser.open(auth_url)
                except Exception:
                    pass

            code = await server_task

            if not code:
                return False, "授权超时或用户取消了授权"

            success = await self._exchange_code_for_token(code)
            if success:
                user_info = await self.fetch_user_info()
                return True, f"授权成功，欢迎 {user_info.name if user_info else ''}"

            else:
                return False, "换取 Token 失败，请重试"
        except Exception as e:
            logger.error("授权流程异常: %s", e, exc_info=True)
            return False, f"授权失败：{e}"
        finally:
            if server_task and not server_task.done():
                server_task.cancel()

    def get_auth_url(self, scope: str = DEFAULT_SCOPE) -> Tuple[str, str]:
        """获取授权页面 URL 和 state（用于手动打开）

        Returns:
            (auth_url, state)
        """
        if not self._load_app_config():
            return "", ""
        try:
            state = secrets.token_urlsafe(16)
            for port in range(CALLBACK_PORT_START, CALLBACK_PORT_END + 1):
                redirect_uri = f"http://127.0.0.1:{port}/callback"
                params = {
                    "app_id": self._app_id,
                    "redirect_uri": redirect_uri,
                    "state": state,
                    "scope": scope,
                }
                from urllib.parse import urlencode
                return f"{AUTHORIZE_URL}?{urlencode(params)}", state
            return "", ""
        except Exception:
            return "", ""

    async def _exchange_code_for_token(self, code: str) -> bool:
        """使用授权码换取 access_token"""
        if not self._load_app_config():
            return False

        try:
            session = self._get_http_session()
            async with session.post(
                ACCESS_TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                },
                headers={
                    "Authorization": f"Bearer {await self._get_app_access_token()}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            ) as resp:
                data = await resp.json()
                if data.get("code") != 0:
                    logger.error("换取 Token 失败: %s", data.get("msg", data))
                    return False

                token_data = data.get("data", {})
                self._access_token = token_data.get("access_token", "")
                self._refresh_token = token_data.get("refresh_token", "")
                expires_in = token_data.get("expires_in", 7200)
                self._expires_at = datetime.now() + timedelta(seconds=int(expires_in))
                self._save_tokens_to_storage()
                self._loaded = True
                return True
        except Exception as e:
            logger.error("换取 Token 异常: %s", e, exc_info=True)
            return False

    async def _refresh_access_token(self) -> bool:
        """使用 refresh_token 刷新 access_token"""
        if not self._load_app_config():
            return False

        if not self._refresh_token:
            return False

        try:
            session = self._get_http_session()
            async with session.post(
                REFRESH_TOKEN_URL,
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                headers={
                    "Authorization": f"Bearer {await self._get_app_access_token()}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            ) as resp:
                data = await resp.json()
                if data.get("code") != 0:
                    logger.error("刷新 Token 失败: %s", data.get("msg", data))
                    return False

                token_data = data.get("data", {})
                self._access_token = token_data.get("access_token", "")
                self._refresh_token = token_data.get("refresh_token", "")
                expires_in = token_data.get("expires_in", 7200)
                self._expires_at = datetime.now() + timedelta(seconds=int(expires_in))
                self._save_tokens_to_storage()
                return True
        except Exception as e:
            logger.error("刷新 Token 异常: %s", e, exc_info=True)
            return False

    async def _get_app_access_token(self) -> str:
        """获取 app_access_token（用于换取 user_access_token）

        注意：此处为简化实现，实际生产环境应缓存 app_access_token 并自动续期。
        此处为 MVP 版本，每次调用都重新获取。
        """
        try:
            session = self._get_http_session()
            async with session.post(
                f"{FEISHU_OPEN_API_BASE}/auth/v3/app_access_token/internal",
                json={
                    "app_id": self._app_id,
                    "app_secret": self._app_secret,
                }
            ) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    return data.get("app_access_token", "")
                else:
                    logger.error("获取 app_access_token 失败，返回数据: %s", data)
        except Exception as e:
            logger.error("获取 app_access_token 失败: %s", e)
        return ""

    # ---------- Token 获取（对外主入口） ----------

    async def get_access_token(self) -> str:
        """获取有效的 access_token（自动续期）

        Raises:
            RuntimeError: 未授权或续期失败
        """
        async with self._token_lock:
            if not self._loaded:
                self._load_tokens_from_storage()
                self._loaded = True

            if not self._access_token:
                raise RuntimeError("飞书账号未授权，请先完成授权")

            now = datetime.now()
            need_refresh = (
                self._expires_at is None
                or (self._expires_at - now).total_seconds()
                < REFRESH_BEFORE_EXPIRE_SECONDS
            )

            if need_refresh:
                if self._refresh_token:
                    success = await self._refresh_access_token()
                    if not success:
                        raise RuntimeError("飞书 Token 已过期且刷新失败，请重新授权")
                else:
                    raise RuntimeError("飞书 Token 已过期且无 refresh_token，请重新授权")

            return self._access_token or ""

    async def fetch_user_info(self) -> Optional[FeishuUserInfo]:
        """获取当前用户信息"""
        try:
            token = await self.get_access_token()
            session = self._get_http_session()
            async with session.get(
                USER_INFO_URL,
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    self._user_info = FeishuUserInfo.from_dict(data.get("data", {}))
                    self._save_tokens_to_storage()
                    return self._user_info
        except Exception as e:
            logger.debug("获取用户信息失败: %s", e)
        return None

    async def revoke_auth(self) -> bool:
        """解除授权（清除本地 Token）

        注意：飞书服务端的授权关系需要用户在飞书授权管理中手动取消。
        """
        async with self._token_lock:
            self._access_token = None
            self._refresh_token = None
            self._expires_at = None
            self._user_info = None
            self._clear_tokens_from_storage()
            return True

    def get_auth_url_for_display(self) -> str:
        """获取授权页面 URL（用于在对话框中展示二维码时调用）

        注意：此方法会立即生成 state 并启动回调服务器等待。
        实际使用时应配合 start_auth_flow 或自定义流程。
        """
        return AUTHORIZE_URL
