"""
认证 API 客户端（闭源实现）
原路径：src/services/auth/auth_api_client.py
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from .auth_config import get_auth_api_base

logger = logging.getLogger(__name__)


def _derive_user_id(username: str) -> int:
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return int(digest, 16) % (2**31 - 1) or 1


async def login(username: str, password: str) -> Dict[str, Any]:
    import aiohttp

    base = get_auth_api_base()
    url = base
    password_sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    payload = {
        "type": "login",
        "username": username,
        "password": password_sha,
        "password_hashed": "sha256",
    }
    result = {"success": False, "code": -1, "msg": "未知错误", "data": None}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                text = await resp.text()
                result["code"] = resp.status
                try:
                    body = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    result["msg"] = "响应格式错误"
                    logger.warning("登录接口返回非 JSON: %s", text[:200])
                    return result

                code = body.get("code", resp.status)
                result["code"] = code
                result["msg"] = body.get("msg", "")
                data = body.get("data") or {}

                if code == 500:
                    logger.debug("云端登录 500 响应体(供云端排查): %s", (text or "")[:500])
                if code == 500 and result["msg"]:
                    if (
                        "Expecting value" in result["msg"]
                        or "JSONDecodeError" in result["msg"]
                        or ("line " in result["msg"] and "column " in result["msg"])
                    ):
                        logger.debug("云端 500 返回技术信息，已替换为友好提示: %s", result["msg"][:100])
                        result["msg"] = "服务异常，请稍后重试"
                if not result["msg"] and code != 200:
                    msg_map = {
                        400: "参数错误",
                        403: "密码错误",
                        404: "账号不存在",
                        429: "登录尝试过于频繁，请稍后再试",
                        500: "服务异常",
                    }
                    result["msg"] = msg_map.get(code, f"请求失败(code={code})")

                if code == 200:
                    result["success"] = True
                    result["data"] = {
                        "username": data.get("username", username),
                        "token": data.get("token"),
                        "level": data.get("level", "vip0"),
                        "expire_time": data.get("expire_time"),
                        "is_expired": data.get("is_expired", True),
                        "user_id": data.get("user_id") or _derive_user_id(username),
                        "max_login_accounts": data.get("max_login_accounts"),
                        "max_account_groups": data.get("max_account_groups"),
                        "daily_max_publish_count": data.get("daily_max_publish_count"),
                        "last_login_at": data.get("last_login_at"),
                        "email": data.get("email"),
                        "phone": data.get("phone"),
                        "wechat_id": data.get("wechat_id"),
                        "create_time": data.get("create_time"),
                        "register_ip": data.get("register_ip"),
                        "last_login_ip": data.get("last_login_ip"),
                    }
                    from src.utils.masking import mask_username
                    logger.info("云端登录成功: username=%s", mask_username(username))
                else:
                    msg_map = {
                        400: "参数错误",
                        403: "密码错误",
                        404: "账号不存在",
                        429: "登录尝试过于频繁，请稍后再试",
                        500: "服务异常",
                    }
                    result["msg"] = result["msg"] or msg_map.get(code, f"请求失败(code={code})")
                    from src.utils.masking import mask_username
                    logger.warning("云端登录失败: code=%s, msg=%s, username=%s", code, result["msg"], mask_username(username))

    except aiohttp.ClientError as e:
        result["msg"] = f"网络请求失败: {e}"
        logger.warning("登录请求异常: %s", e)
    except Exception as e:
        result["msg"] = f"登录出错: {e}"
        logger.exception("登录异常")

    return result


async def refresh_user_info(token: str) -> Dict[str, Any]:
    import aiohttp

    base = get_auth_api_base()
    payload = {"type": "refresh_user_info", "token": token}
    result = {"success": False, "data": None, "msg": "未知错误"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                base,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                text = await resp.text()
                try:
                    body = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    result["msg"] = "响应格式错误"
                    return result
                code = body.get("code", resp.status)
                if code == 200:
                    result["success"] = True
                    result["data"] = body.get("data") or {}
                else:
                    result["msg"] = body.get("msg") or f"刷新失败(code={code})"
    except aiohttp.ClientError as e:
        result["msg"] = f"网络请求失败: {e}"
        logger.warning("refresh_user_info 请求异常: %s", e)
    except Exception as e:
        result["msg"] = str(e)
        logger.exception("refresh_user_info 异常")
    return result


async def publish_check(token: str, platform: str, is_pro_platform: bool) -> Dict[str, Any]:
    import aiohttp

    base = get_auth_api_base()
    payload = {
        "type": "publish_check",
        "token": token,
        "platform": platform,
        "is_pro_platform": is_pro_platform,
    }
    result = {"success": False, "allowed": False, "reason": "未知错误"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                base,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                text = await resp.text()
                try:
                    body = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    result["reason"] = "响应格式错误"
                    return result
                data = body.get("data") or {}
                result["success"] = True
                result["allowed"] = bool(data.get("allowed"))
                result["reason"] = data.get("reason") or ("未通过校验" if not result["allowed"] else "")
                result["code"] = data.get("code")
                if not result["allowed"] and not result["reason"]:
                    result["reason"] = "未通过校验"
    except aiohttp.ClientError as e:
        result["reason"] = f"网络请求失败: {e}"
        logger.warning("publish_check 请求异常: %s", e)
    except Exception as e:
        result["reason"] = str(e)
        logger.exception("publish_check 异常")
    return result


async def register(
    username: str,
    password: str,
    email: str = "",
    phone: Optional[str] = None,
    wechat_id: Optional[str] = None,
) -> Dict[str, Any]:
    import aiohttp

    base = get_auth_api_base()
    url = base
    password_sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    payload = {
        "username": username,
        "password": password_sha,
        "password_hashed": "sha256",
        "email": email or "",
        "phone": (phone or "").strip(),
        "wechat_id": (wechat_id or "").strip(),
        "type": "register",
    }
    result = {"success": False, "code": -1, "msg": "未知错误", "user_id": None}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                text = await resp.text()
                result["code"] = resp.status
                try:
                    body = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    result["msg"] = "响应格式错误"
                    logger.warning("注册接口返回非 JSON: %s", text[:200])
                    return result

                code = body.get("code", resp.status)
                result["code"] = code
                result["msg"] = body.get("msg", "")

                if resp.status in (200, 201) or code in (200, 201):
                    result["success"] = True
                    data = body.get("data") or body
                    result["user_id"] = data.get("user_id") or data.get("id") or _derive_user_id(username)
                    from src.utils.masking import mask_username
                    logger.info("云端注册成功: username=%s", mask_username(username))
                else:
                    msg_map = {400: "参数错误", 409: "用户名已存在", 500: "服务异常"}
                    result["msg"] = result["msg"] or msg_map.get(code, f"注册失败(code={code})")
                    logger.warning("云端注册失败: code=%s, msg=%s", code, result["msg"])

    except aiohttp.ClientError as e:
        result["msg"] = f"网络请求失败: {e}"
        logger.warning("注册请求异常: %s", e)
    except Exception as e:
        result["msg"] = f"注册出错: {e}"
        logger.exception("注册异常")

    return result

