"""
账号管理模块（异步版本）
文件路径：src/services/account/account_manager_async.py
功能：管理平台账号的添加、删除、切换、状态验证等（异步版本）
已迁移：使用 AccountRepositoryAsync 替代 AsyncDataStorage
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
import logging
import os
import asyncio
import uuid

from src.infrastructure.common.event.event_bus import EventBus
from src.infrastructure.common.event.events import AccountAddedEvent, AccountRemovedEvent
from src.infrastructure.common.di.service_locator import ServiceLocator
from src.services.account.cookie_manager import CookieManager, COOKIE_FILENAME
from src.domain.repositories.account_repository_async import AccountRepositoryAsync
from src.utils.file_utils import ensure_directory_exists
from src.utils.date_utils import get_current_datetime_str
from src.infrastructure.common.path_manager import PathManager

logger = logging.getLogger(__name__)


class AccountManagerAsync:
    """账号管理器（异步版本）- 负责平台账号的管理
    
    使用 Repository 模式分离数据访问逻辑，所有操作都是异步的。
    """
    
    def __init__(
        self,
        user_id: int,
        event_bus: Optional[EventBus] = None
    ):
        """初始化账号管理器
        
        Args:
            user_id: 用户ID
            event_bus: 事件总线（可选，默认从ServiceLocator获取）
        """
        self.user_id = user_id
        self.service_locator = ServiceLocator()
        self.event_bus = event_bus or self.service_locator.get(EventBus)
        
        # 使用 AccountRepositoryAsync 进行数据访问（已完成从 AsyncDataStorage 迁移）
        self.account_repository = AccountRepositoryAsync()
        self.cookie_manager = CookieManager()
        self.current_account: Optional[Dict[str, Any]] = None
        self.verifier = None  # 延迟初始化，避免循环导入
        self.logger = logging.getLogger(__name__)
        # 串行化同一用户的添加账号操作，避免并发时 exists 与 create 之间竞态导致重复创建
        self._add_account_lock = asyncio.Lock()

    async def _try_sync_material_library(self) -> None:
        """已配置媒体库时，同步「账号库」下账号与账号组素材目录；失败不抛给业务层。"""
        try:
            from src.infrastructure.common.material_library_manager import MaterialLibraryManager

            await MaterialLibraryManager.sync_platform_account_tree()
        except Exception as e:
            self.logger.debug("同步媒体库目录树失败（可忽略）: %s", e)
    
    async def add_account(
        self,
        platform: str,
        platform_username: str,
        browser: Optional[Any] = None,  # 保留参数兼容，实际使用 Playwright
        cookie_data: Optional[Dict[str, Any]] = None,
        profile_folder_name: Optional[str] = None
    ) -> int:
        """添加平台账号（异步）
        
        Args:
            platform: 平台名称（douyin/kuaishou/xiaohongshu）
            platform_username: 平台账号昵称（必需）
            browser: 浏览器实例（可选，用于提取Cookie）
            cookie_data: Cookie数据（可选，如果提供则直接使用）
            profile_folder_name: 账号数据文件夹名称(UUID/TempName)，如有则优先使用
        
        Returns:
            新创建的账号ID
        
        Raises:
            ValueError: 账号昵称已存在、已达账号数量上限或参数无效
        """
        async with self._add_account_lock:
            return await self._add_account_impl(
                platform=platform,
                platform_username=platform_username,
                browser=browser,
                cookie_data=cookie_data,
                profile_folder_name=profile_folder_name,
            )

    async def add_placeholder_account(self, platform: str) -> tuple:
        """添加占位账号（先占位、后更新流程）

        在用户选择平台后立即创建一条占位账号，平台昵称为「待登录」，无 Cookie。
        用户在浏览器中完成登录后，通过 update_account_after_login 更新该账号。

        Args:
            platform: 平台名称（douyin/kuaishou/xiaohongshu/wechat_video）

        Returns:
            (account_id, profile_folder_name) 元组
        """
        profile_folder_name = f"profile_{uuid.uuid4().hex[:12]}"
        placeholder_username = "待登录"

        # 创建账号文件夹（与 _add_account_impl 一致）
        account_root = PathManager.get_platform_account_dir(platform, placeholder_username, profile_folder_name)
        workspace_dir = account_root / "workspace"
        ensure_directory_exists(str(workspace_dir))
        ensure_directory_exists(str(workspace_dir / "media"))
        ensure_directory_exists(str(workspace_dir / "logs"))
        ensure_directory_exists(str(workspace_dir / "temp"))
        ensure_directory_exists(str(workspace_dir / "media" / "pending"))
        ensure_directory_exists(str(workspace_dir / "media" / "published"))
        self.logger.info(f"创建占位账号工作目录: {workspace_dir} (Profile: {profile_folder_name})")

        # 直接调用 repository.create，不经过 add_account（避免 exists 校验）
        account_id = await self.account_repository.create(
            user_id=self.user_id,
            platform=platform,
            platform_username=placeholder_username,
            cookie_path="",
            profile_folder_name=profile_folder_name,
        )
        self.logger.info(f"创建占位账号成功: platform={platform}, account_id={account_id}, profile={profile_folder_name}")
        await self._try_sync_material_library()
        return (account_id, profile_folder_name)

    async def update_account_after_login(
        self,
        account_id: int,
        platform_username: str,
        cookie_data: Dict[str, Any],
    ) -> None:
        """登录成功后更新占位账号（先占位、后更新流程）

        将占位账号的平台昵称、Cookie、登录状态更新为真实值。

        Args:
            account_id: 占位账号 ID
            platform_username: 真实平台昵称
            cookie_data: Cookie 数据
        """
        await self.update_platform_username(account_id, platform_username)
        # update_cookie 内部已更新 login_status=online、last_login_at，无需重复 update_status
        await self.update_cookie(account_id, cookie_data)
        self.logger.info(f"占位账号更新完成: account_id={account_id}, nickname={platform_username}")

    async def _add_account_impl(
        self,
        platform: str,
        platform_username: str,
        browser: Optional[Any] = None,
        cookie_data: Optional[Dict[str, Any]] = None,
        profile_folder_name: Optional[str] = None,
    ) -> int:
        """添加账号的实际实现（在 _add_account_lock 内调用，避免并发重复创建）。
        约定：只使用 profile_xxx 作为数据目录，不生成以平台昵称命名的文件夹。
        profile_folder_name 必填（或在此生成），否则打开浏览器、Cookie 路径、验证等都会报错。"""
        # 未传 profile 时自动生成，避免产生 data/{platform}/{平台昵称} 目录导致路径混乱与 Cookie 找不到
        if not (profile_folder_name and profile_folder_name.strip()):
            profile_folder_name = f"profile_{uuid.uuid4().hex[:12]}"
            self.logger.info(
                "添加账号未提供 profile_folder_name，已生成: %s（请确保新账号流程传入 _current_temp_name）",
                profile_folder_name,
            )

        # 额度校验：云端返回了 max_login_accounts 时，禁止超出
        from src.services.auth.current_user_service import CurrentUserService
        max_accounts = CurrentUserService().get_max_login_accounts()
        if max_accounts is not None:
            existing = await self.account_repository.find_all(user_id=self.user_id)
            if len(existing) >= max_accounts:
                raise ValueError(
                    f"已达最大登录账号数量上限（{max_accounts}），请升级会员或联系客服。"
                )
        # 验证账号昵称唯一性（使用 Repository）
        if await self.account_repository.exists(self.user_id, platform_username, platform):
            raise ValueError(f"账号昵称已存在: {platform_username}")

        # 创建账号文件夹：仅使用 profile_folder_name，不再用 platform_username 作为目录名
        account_root = PathManager.get_platform_account_dir(platform, platform_username, profile_folder_name)
        workspace_dir = account_root / "workspace"
        
        # 确保工作区及子目录存在
        ensure_directory_exists(str(workspace_dir))
        ensure_directory_exists(str(workspace_dir / "media"))
        ensure_directory_exists(str(workspace_dir / "logs"))
        ensure_directory_exists(str(workspace_dir / "temp"))
        ensure_directory_exists(str(workspace_dir / "media" / "pending")) # 待发布
        ensure_directory_exists(str(workspace_dir / "media" / "published")) # 已发布
        
        self.logger.info(f"创建账号工作目录: {workspace_dir} (Profile: {profile_folder_name or 'Legacy'})")
        
        # 处理Cookie
        cookie_path = ""
        if cookie_data:
            # 如果提供了Cookie数据，直接保存
            cookie_path = self.cookie_manager.save_cookie(
                platform_username,
                platform,
                cookie_data,
                profile_folder_name
            )
            self.logger.info(f"保存Cookie成功: {cookie_path}")
        elif browser:
            # 如果提供了浏览器实例，提取Cookie
            try:
                cookies = browser.extract_cookies_dict()
                if cookies:
                    cookie_path = self.cookie_manager.save_cookie(
                        platform_username,
                        platform,
                        cookies,
                        profile_folder_name
                    )
                    self.logger.info(f"提取并保存Cookie成功: {cookie_path}")
            except Exception as e:
                self.logger.warning(f"提取Cookie失败: {e}")
        
        # 创建账号记录（通过 Repository）
        account_id = await self.account_repository.create(
            user_id=self.user_id,
            platform=platform,
            platform_username=platform_username,
            cookie_path=cookie_path,
            profile_folder_name=profile_folder_name
        )
        
        # 如果有 Cookie，更新账号状态为在线
        if cookie_path:
            await self.account_repository.update_status(
                account_id=account_id,
                login_status='online',
                last_login_at=get_current_datetime_str()
            )
        
        # 发布事件（异步）
        if self.event_bus:
            event = AccountAddedEvent(
                user_id=self.user_id,
                platform_username=platform_username,
                platform=platform
            )
            await self.event_bus.publish(event)
        
        self.logger.info(
            f"添加账号成功: {platform_username}, 平台: {platform}, ID: {account_id}"
        )

        await self._try_sync_material_library()

        return account_id
    
    async def get_accounts(
        self,
        platform: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取账号列表（异步）
        
        单用户模式：不区分软件是否登录，始终返回本地所有平台账号，
        保证「无论登录与否，列表都显示本地已登录的全部平台账号」。
        
        Args:
            platform: 平台名称（可选，如果指定则只返回该平台的账号）
        
        Returns:
            账号列表
        """
        return await self.account_repository.find_all(
            user_id=None,
            platform=platform
        )
    
    async def get_account_by_id(
        self,
        account_id: int
    ) -> Optional[Dict[str, Any]]:
        """根据账号ID获取账号信息（异步）
        
        Args:
            account_id: 账号ID
        
        Returns:
            账号信息字典，如果不存在返回None
        """
        # 使用 Repository 查找账号
        return await self.account_repository.find_by_id(
            user_id=self.user_id,
            account_id=account_id
        )

    async def ensure_account_has_profile_folder(self, account_id: int) -> bool:
        """若账号缺少 profile_folder_name，则从磁盘 data/{platform}/ 下发现唯一的 profile_* 目录并回填。
        用于修复「有账号数据文件夹但 DB 未记录 profile」导致的打不开浏览器、Cookie 文件不存在等问题。
        Returns:
            True 表示账号已有或已回填 profile_folder_name，可正常打开浏览器；False 表示无法解析。
        """
        account = await self.get_account_by_id(account_id)
        if not account:
            return False
        if account.get("profile_folder_name") and str(account.get("profile_folder_name")).strip():
            return True
        platform = (account.get("platform") or "").strip()
        if not platform:
            return False
        data_platform = PathManager.get_app_data_dir() / "data" / platform
        if not data_platform.exists() or not data_platform.is_dir():
            return False
        profiles = [
            d.name for d in data_platform.iterdir()
            if d.is_dir() and d.name.startswith("profile_")
        ]
        if len(profiles) == 1:
            profile_name = profiles[0]
            cookie_path = str(data_platform / profile_name / COOKIE_FILENAME)
            ok = await self.account_repository.update_profile_folder_name(
                account_id, profile_name, cookie_path
            )
            if ok:
                self.logger.info(
                    "已回填账号 profile_folder_name: account_id=%s, profile=%s",
                    account_id, profile_name,
                )
            return ok
        if len(profiles) == 0:
            # 该平台下无任何 profile 目录，为账号新建 profile，便于打开浏览器并重新登录
            profile_name = f"profile_{uuid.uuid4().hex[:12]}"
            ok = await self.account_repository.update_profile_folder_name(
                account_id, profile_name, ""
            )
            if ok:
                self.logger.info(
                    "已为账号新建 profile_folder_name: account_id=%s, profile=%s",
                    account_id, profile_name,
                )
            return ok
        # 多个 profile 无法自动绑定，避免误绑
        self.logger.warning(
            "平台 %s 下存在多个 profile_* 目录（%s），无法自动绑定账号 account_id=%s，请通过双击打开浏览器使用对应账号后再刷新状态",
            platform, profiles, account_id,
        )
        return False

    async def get_account_for_operation(self, account_id: int) -> Optional[Dict[str, Any]]:
        """获取用于操作的账号信息（先 ensure profile_folder_name 再取最新数据，供指纹/删除等不依赖表格缓存）。"""
        await self.ensure_account_has_profile_folder(account_id)
        return await self.get_account_by_id(account_id)
    
    async def switch_account(self, account_id: int) -> bool:
        """切换当前账号（异步）
        
        Args:
            account_id: 账号ID
        
        Returns:
            如果切换成功返回True，否则返回False
        """
        account = await self.get_account_by_id(account_id)
        if not account:
            self.logger.warning(f"账号不存在: ID {account_id}")
            return False
        
        self.current_account = account
        self.logger.info(
            f"切换账号成功: {account['platform_username']}, 平台: {account['platform']}"
        )
        return True
    
    def get_current_account(self) -> Optional[Dict[str, Any]]:
        """获取当前账号
        
        Returns:
            当前账号信息，如果未设置返回None
        """
        return self.current_account
    
    async def verify_account_status(
        self,
        account_id: int,
        browser: Optional[Any] = None
    ) -> bool:
        """验证账号状态（检查Cookie是否可加载）（异步）
        
        走统一的 load_account_cookie 路径，与刷新登录状态逻辑保持一致。
        
        Args:
            account_id: 账号ID
            browser: 浏览器实例（可选，用于验证）
        
        Returns:
            如果账号有效返回True，否则返回False
        """
        cookie_data = await self.load_account_cookie(account_id, merge_storage_state=True)
        if not cookie_data:
            account = await self.get_account_by_id(account_id)
            self.logger.warning(
                "Cookie不可用: %s, 平台: %s",
                account.get('platform_username', '?') if account else '?',
                account.get('platform', '?') if account else '?',
            )
            await self.update_account_login_status(account_id, "offline", publish_event=True)
            return False

        await self.update_account_login_status(account_id, "online", publish_event=True)
        return True

    async def update_account_login_status(
        self,
        account_id: int,
        login_status: str,
        *,
        publish_event: bool = True,
    ) -> bool:
        """更新账号登录状态（online/offline）并写库。

        - publish_event=True：发布 AccountUpdatedEvent，账号库等订阅方会刷新列表（单点更新、发布列表掉线同步等）。
        - publish_event=False：仅写库，用于批量 HTTP 验证等场景（由验证进度信号与结束时的 reload 更新 UI，避免 N 次全表刷新）。
        """
        ok = await self.account_repository.update_status(
            account_id=account_id,
            login_status=login_status,
        )
        if ok and publish_event and self.event_bus:
            try:
                from src.infrastructure.common.event.events import AccountUpdatedEvent

                event = AccountUpdatedEvent(
                    user_id=self.user_id,
                    account_id=account_id,
                    update_type="state",
                )
                await self.event_bus.publish(event)
            except Exception as e:
                self.logger.warning("发布 AccountUpdatedEvent（登录状态）失败: %s", e)
        return ok
    
    async def verify_all_accounts_status(self) -> None:
        """验证所有账号的状态（异步）
        
        使用 AccountVerifier 通过 HTTP 请求批量验证账号状态。
        """
        try:
            # 延迟导入并初始化验证器
            if not self.verifier:
                from .account_verifier import AccountVerifier
                self.verifier = AccountVerifier(self)
                
            accounts = await self.get_accounts()
            if not accounts:
                return

            self.logger.info("开始执行 HTTP 批量验证...")
            
            # 使用验证器进行批量验证
            # 验证结果会自动通过 data_storage 更新到数据库
            await self.verifier.verify_accounts_batch(accounts)
            
            self.logger.info(f"已完成所有账号的 HTTP 状态验证（共 {len(accounts)} 个）")
            
        except Exception as e:
            self.logger.error(f"验证所有账号状态失败: {e}", exc_info=True)

    
    async def delete_account(
        self,
        account_id: int,
        delete_cookie: bool = False,
        delete_records: bool = False
    ) -> bool:
        """删除账号(异步)
        
        Args:
            account_id: 账号ID
            delete_cookie: 是否同时删除Cookie文件和浏览器数据
            delete_records: 是否同时删除发布记录
        
        Returns:
            如果删除成功返回True,否则返回False
        """
        account = await self.get_account_for_operation(account_id)
        if not account:
            self.logger.warning(f"账号不存在: ID {account_id}")
            return False
        
        account_username = account['platform_username']
        platform = account['platform']
        
        # 删除Cookie文件和账号数据目录
        if delete_cookie:
            import shutil
            from pathlib import Path
            profile_folder = (account.get("profile_folder_name") or "").strip()
            cookie_path = (account.get("cookie_path") or "").strip()
            account_dir = None
            if profile_folder:
                self.cookie_manager.delete_cookie(account_username, platform, profile_folder)
                account_dir = PathManager.get_platform_account_dir(platform, account_username, profile_folder)
            elif cookie_path and Path(cookie_path).exists():
                account_dir = Path(cookie_path).parent
                try:
                    if account_dir.exists():
                        for fname in (COOKIE_FILENAME,):
                            cf = account_dir / fname
                            if cf.exists():
                                cf.unlink(missing_ok=True)
                except Exception as e:
                    self.logger.warning(f"删除 Cookie 文件失败: {e}")
            else:
                account_dir = None
            if account_dir and account_dir.exists():
                try:
                    self.logger.info(f"删除账号数据目录: {account_dir}")
                    shutil.rmtree(account_dir, ignore_errors=True)
                except Exception as e:
                    self.logger.error(f"删除账号数据目录失败: {e}", exc_info=True)
        
        # 删除发布记录(如果需要)
        if delete_records:
            # 注意:这里需要实现删除发布记录的功能
            # 暂时只记录日志
            self.logger.info(f"删除发布记录: 账号={account_username}")
        
        # 删除数据库记录(使用 Repository)
        await self.account_repository.delete(account_id)
        
        # 发布事件(异步)
        if self.event_bus:
            event = AccountRemovedEvent(
                user_id=self.user_id,
                platform_username=account_username,
                platform=platform
            )
            await self.event_bus.publish(event)
        
        # 如果删除的是当前账号,清空当前账号
        if self.current_account and self.current_account['id'] == account_id:
            self.current_account = None
        
        self.logger.info(f"删除账号成功: {account_username}, 平台: {platform}")
        return True
    
    async def update_platform_username(
        self,
        account_id: int,
        platform_username: str
    ) -> bool:
        """更新平台用户名（异步）
        
        Args:
            account_id: 账号ID
            platform_username: 平台用户名
            
        Returns:
            如果更新成功返回True，否则返回False
        """
        try:
            old_account = await self.account_repository.find_by_id(account_id)
            old_username = str((old_account or {}).get("platform_username") or "").strip()
            old_platform = str((old_account or {}).get("platform") or "").strip()
            # 使用 Repository 更新平台用户名
            success = await self.account_repository.update_platform_username(
                account_id=account_id,
                platform_username=platform_username
            )
            if success:
                self.logger.info(
                    f"更新平台用户名成功: 账号ID={account_id}, 用户名={platform_username}"
                )
                try:
                    if old_username and old_platform and old_username != platform_username:
                        MaterialLibraryManager.rename_platform_account_folder(
                            old_platform,
                            old_username,
                            platform_username,
                        )
                except Exception as _rename_e:
                    self.logger.warning("账号素材目录重命名失败: %s", _rename_e)
                
                # 发布更新事件
                if self.event_bus:
                    from src.infrastructure.common.event.events import AccountUpdatedEvent
                    event = AccountUpdatedEvent(
                        user_id=self.user_id,
                        account_id=account_id,
                        update_type='nickname'
                    )
                    await self.event_bus.publish(event)

                await self._try_sync_material_library()

            return success
        except Exception as e:
            self.logger.error(f"更新平台用户名失败: {e}")
            return False
    
    async def clear_cookie(self, account_id: int) -> bool:
        """清理Cookie（删除Cookie文件，需要重新登录）（异步）
        
        Args:
            account_id: 账号ID
        
        Returns:
            如果清理成功返回True，否则返回False
        """
        account = await self.get_account_by_id(account_id)
        if not account:
            return False
        
        # 删除Cookie文件
        success = self.cookie_manager.delete_cookie(
            account['platform_username'],
            account['platform'],
            account.get('profile_folder_name')
        )
        
        if success:
            # 更新账号状态
            await self.account_repository.update_status(
                account_id=account_id,
                login_status='offline'
            )
            self.logger.info(
                f"清理Cookie成功: {account['platform_username']}, "
                f"平台: {account['platform']}"
            )
        
        return success
    
    async def update_cookie(
        self,
        account_id: int,
        cookie_data: Dict[str, Any],
        *,
        update_status: bool = True,
    ) -> bool:
        """更新账号Cookie（异步）
        
        Args:
            account_id: 账号ID
            cookie_data: Cookie数据
            update_status: 为 True 时同时将登录状态置为 online 并更新 last_login_at；
                为 False 时仅写入 cookies.json 与 cookie_path（用于已判离线仅同步磁盘场景）。
        
        Returns:
            如果更新成功返回True，否则返回False
        """
        account = await self.get_account_by_id(account_id)
        if not account:
            return False
        
        try:
            cookie_path = self.cookie_manager.save_cookie(
                account['platform_username'],
                account['platform'],
                cookie_data,
                account.get('profile_folder_name')
            )
            # 同步写入数据库，否则验证/刷新登录状态时仍按旧路径找文件会报「Cookie文件不存在」
            await self.account_repository.update_cookie_path(account_id, cookie_path)

            if update_status:
                # 更新账号状态
                await self.account_repository.update_status(
                    account_id=account_id,
                    login_status='online',
                    last_login_at=get_current_datetime_str()
                )
                
                # 发布更新事件
                if self.event_bus:
                    from src.infrastructure.common.event.events import AccountUpdatedEvent
                    event = AccountUpdatedEvent(
                        user_id=self.user_id,
                        account_id=account_id,
                        update_type='status' # cookie 更新意味着状态更新为 online
                    )
                    await self.event_bus.publish(event)

            
            self.logger.info(f"更新Cookie成功: {cookie_path}")
            return True
        except Exception as e:
            self.logger.error(f"更新Cookie失败: {e}")
            return False

    async def load_account_cookie(
        self,
        account_id: int,
        *,
        merge_storage_state: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """加载账号Cookie（异步）

        加载前先 ensure_profile，再按 profile_folder_name 从 cookies.json 读取。

        Args:
            account_id: 账号ID
            merge_storage_state: 为 True 时合并 ``browser/storage_state.json`` 中尚未出现在
                cookies.json 的项，并归一为扁平 name->value。用于刷新登录状态、发布前 HTTP 检测、
                注入浏览器等，与持久化 Profile 中实际登录态对齐。

        Returns:
            Cookie数据；无任何可用 Cookie 时返回 None
        """
        from src.services.account.cookie_manager import normalize_to_flat_cookie_dict

        await self.ensure_account_has_profile_folder(account_id)
        account = await self.get_account_by_id(account_id)
        if not account:
            return None

        # load_cookie / merge_storage_state 均为同步磁盘读取，移到线程池避免阻塞事件循环
        import asyncio as _asyncio
        raw = await _asyncio.to_thread(
            self.cookie_manager.load_cookie,
            account['platform_username'],
            account['platform'],
            account.get('profile_folder_name'),
        )

        if not merge_storage_state:
            return raw

        flat = normalize_to_flat_cookie_dict(raw) if raw else {}
        merged = await _asyncio.to_thread(
            self.cookie_manager.merge_storage_state_into_flat_cookies,
            account.get('platform_username') or '',
            account.get('platform') or '',
            account.get('profile_folder_name'),
            flat,
        )
        return merged if merged else None
