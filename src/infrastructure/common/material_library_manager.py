"""
媒体库管理器
文件路径：src/infrastructure/common/material_library_manager.py
功能：统一管理「媒小宝媒体库」根路径、静态目录初始化，以及在「账号库」下按账号/账号组同步「视频」「图文」子目录。

目录结构约定（root_base 为用户在设置中选择的物理目录，例如 D:\\MediaLib）：
    root_base/
        媒小宝媒体库/
            视频库/          # 未绑定账号前的公共视频
            图片库/          # 未绑定账号前的公共图片
            账号库/          # 所有账号与账号组素材根目录（一级为账号文件夹或账号组文件夹）
                <平台中文名>_<账号昵称>/
                    视频/
                        已发布/
                        未发布/
                    图文/
                        已发布/
                        未发布/
                账号组_<组名>/
                    视频/
                        已发布/
                        未发布/
                    图文/
                        已发布/
                        未发布/

注意：
- 根路径由 ConfigCenter 的 app_config.material_library_root 管理；
- 读写配置**仅**通过本类的 _get_config_center() → **优先** main 启动时注册的 ConfigCenter 单例
  （`get_registered_config_center()`），与开发/生产共用同一持久化文件：
  ``PathManager.get_config_dir() / app_config.json``，避免无参 new ConfigCenter 与单例读写分离；
- 仅在用户从设置页选择路径后才进行初始化；
- 所有异常需记录日志，并由上层 UI 弹出友好提示。
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional, Iterable, Dict, Any, List

from src.infrastructure.common.config.config_center import ConfigCenter, get_registered_config_center
from src.domain.repositories.account_repository_async import AccountRepositoryAsync

logger = logging.getLogger(__name__)


class MaterialLibraryManager:
    """媒体库管理器 - 负责路径配置、目录初始化和账号/账号组素材子目录同步。"""

    # ConfigCenter.app_config 中使用的配置键
    APP_CONFIG_KEY = "app_config"
    APP_CONFIG_FIELD = "material_library_root"

    ROOT_FOLDER_NAME = "媒小宝媒体库"
    VIDEO_FOLDER_NAME = "视频库"
    IMAGE_FOLDER_NAME = "图片库"
    # 原「平台账号」目录现统一为「账号库」：其下一级仅为账号文件夹或「账号组_xxx」文件夹
    ACCOUNT_LIBRARY_FOLDER_NAME = "账号库"
    PUBLISHED_NAME = "已发布"
    UNPUBLISHED_NAME = "未发布"
    # 账号/组下一级素材分类
    ACCOUNT_MEDIA_VIDEO_NAME = "视频"
    ACCOUNT_MEDIA_IMAGE_NAME = "图文"
    # 账号组文件夹名前缀：`账号组_<组名>`，与导航菜单「账号组」概念对应但为磁盘上的不同命名空间
    GROUP_MATERIAL_PREFIX = "账号组_"

    @classmethod
    def sanitize_path_segment(cls, raw: str) -> str:
        """去掉首尾空白，替换 Windows 非法文件名字符。"""
        if raw is None:
            return ""
        s = str(raw).strip()
        if not s:
            return ""
        s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
        s = s.rstrip(" .")
        return s

    @classmethod
    def account_library_root(cls, media_root: Path) -> Path:
        """媒小宝媒体库根下的「账号库」路径。"""
        return media_root / cls.ACCOUNT_LIBRARY_FOLDER_NAME

    @classmethod
    def platform_account_folder_name(cls, platform_id: str, platform_username: str) -> str:
        """单个平台账号在「账号库」下的一级文件夹名：`平台名称_账号昵称`（平台名称为中文展示名）。"""
        from src.utils.platform_names import get_platform_display_name

        plat_label = cls.sanitize_path_segment(
            get_platform_display_name((platform_id or "").strip())
        ) or "未知平台"
        nick = cls.sanitize_path_segment(
            platform_username or ""
        ) or "未命名账号"
        return f"{plat_label}_{nick}"

    @classmethod
    def account_group_material_folder_name(cls, group_name: str) -> str:
        """账号组在「账号库」下的一级文件夹名：`账号组_账号组名称`。"""
        body = cls.sanitize_path_segment(group_name or "") or "未命名"
        return f"{cls.GROUP_MATERIAL_PREFIX}{body}"

    @classmethod
    def owner_label_for_group_material_folder(cls, folder_name: str) -> str:
        """子目录固定为 `账号组_<组名>`，列表中展示为 `账号组-<组名>`。"""
        name = folder_name or ""
        rest = name.removeprefix(cls.GROUP_MATERIAL_PREFIX)
        return "账号组-" + rest if rest else "账号组"

    @classmethod
    def owner_label_for_account_library_entry(cls, folder_name: str) -> str:
        """扫描「账号库」一级子目录时，生成视频归属展示文案。"""
        name = folder_name or ""
        if name.startswith(cls.GROUP_MATERIAL_PREFIX):
            return cls.owner_label_for_group_material_folder(name)
        return name

    @classmethod
    def _ensure_video_image_branches(cls, owner_folder: Path) -> None:
        """在某一账号或账号组文件夹下创建 视频/图文 × 已发布/未发布。"""
        for media in (cls.ACCOUNT_MEDIA_VIDEO_NAME, cls.ACCOUNT_MEDIA_IMAGE_NAME):
            base = owner_folder / media
            (base / cls.PUBLISHED_NAME).mkdir(parents=True, exist_ok=True)
            (base / cls.UNPUBLISHED_NAME).mkdir(parents=True, exist_ok=True)

    @classmethod
    def account_video_unpublished_dir(cls, root: Path, account: Dict[str, Any]) -> Path:
        """某账号下「视频 / 未发布」目录。"""
        lib = cls.account_library_root(root)
        folder = cls.platform_account_folder_name(
            str(account.get("platform") or ""),
            str(
                account.get("platform_username")
                or account.get("account_name")
                or ""
            ),
        )
        return lib / folder / cls.ACCOUNT_MEDIA_VIDEO_NAME / cls.UNPUBLISHED_NAME

    @classmethod
    def account_library_owner_folder_matches_account(
        cls, owner_folder_name: str, account: Dict[str, Any]
    ) -> bool:
        """判断「账号库」下一级目录名是否归属该账号（与 resolve_*_unpublished_dir 昵称规则一致）。

        ``owner_folder_name`` 为磁盘上的一级文件夹名（与视频库/图片库扫描里账号的 owner_label 一致）。
        ``账号组_*`` 目录返回 False，由账号组维度统计单独处理。
        """
        name = str(owner_folder_name or "").strip()
        if not name or not isinstance(account, dict):
            return False
        if name.startswith(cls.GROUP_MATERIAL_PREFIX):
            return False

        platform_id = str(account.get("platform") or "").strip()
        from src.utils.platform_names import get_platform_display_name

        plat_label = cls.sanitize_path_segment(get_platform_display_name(platform_id)) or "未知平台"

        nick_order: List[str] = []
        for key in ("platform_username", "account_name"):
            raw = (account.get(key) or "").strip()
            if raw and raw not in nick_order:
                nick_order.append(raw)

        def _nick_norm(s: str) -> str:
            return unicodedata.normalize("NFKC", (s or "").strip()).casefold()

        for nick in nick_order:
            folder = cls.platform_account_folder_name(platform_id, nick)
            if name == folder:
                return True

        nick_norms = [_nick_norm(n) for n in nick_order if n]
        prefix = f"{plat_label}_"
        if not name.startswith(prefix):
            return False
        suffix = name[len(prefix) :]
        sn = _nick_norm(suffix)
        for nn in nick_norms:
            if not nn:
                continue
            if sn == nn:
                return True
            if len(nn) >= 2 and len(sn) >= 2 and (nn in sn or sn in nn):
                return True
        return False

    @classmethod
    def _resolve_account_media_unpublished_dir(
        cls, root: Path, account: Dict[str, Any], media_branch: str
    ) -> Path:
        """解析账号下「视频或图文 / 未发布」目录（规范路径优先，其次文件夹名模糊匹配）。"""
        lib = cls.account_library_root(root)
        platform_id = str(account.get("platform") or "").strip()
        from src.utils.platform_names import get_platform_display_name

        plat_label = cls.sanitize_path_segment(get_platform_display_name(platform_id)) or "未知平台"

        nick_order: List[str] = []
        for key in ("platform_username", "account_name"):
            raw = (account.get(key) or "").strip()
            if raw and raw not in nick_order:
                nick_order.append(raw)

        for nick in nick_order:
            folder = cls.platform_account_folder_name(platform_id, nick)
            p = lib / folder / media_branch / cls.UNPUBLISHED_NAME
            if p.exists():
                return p

        prefix = f"{plat_label}_"
        try:
            for entry in os.scandir(str(lib)):
                if not entry.is_dir():
                    continue
                name = entry.name
                if not name.startswith(prefix):
                    continue
                if not cls.account_library_owner_folder_matches_account(name, account):
                    continue
                cand = Path(entry.path) / media_branch / cls.UNPUBLISHED_NAME
                if cand.exists():
                    logger.info(
                        "账号素材目录使用模糊匹配: 期望前缀 %r 下选用 %r（标准路径不存在）",
                        prefix,
                        name,
                    )
                    return cand
        except OSError as e:
            logger.debug("模糊匹配账号素材目录失败: %s", e)

        folder = cls.platform_account_folder_name(
            str(account.get("platform") or ""),
            str(account.get("platform_username") or account.get("account_name") or ""),
        )
        return lib / folder / media_branch / cls.UNPUBLISHED_NAME

    @classmethod
    def resolve_account_video_unpublished_dir(cls, root: Path, account: Dict[str, Any]) -> Path:
        """解析账号「视频 / 未发布」目录（与视频库扫描一致）。

        先按 platform + platform_username / account_name 计算标准路径；
        若不存在，再在「账号库」下按「平台中文名_」前缀做文件夹名模糊匹配。

        用于解决：磁盘上实际文件夹与当前昵称略有差异（易混字、手工改名、历史同步差异）时，
        视频库列表能看到文件而批量自动匹配却扫到空目录的问题。
        """
        return cls._resolve_account_media_unpublished_dir(root, account, cls.ACCOUNT_MEDIA_VIDEO_NAME)

    @classmethod
    def resolve_account_image_unpublished_dir(cls, root: Path, account: Dict[str, Any]) -> Path:
        """解析账号「图文 / 未发布」目录（与 resolve_account_video_unpublished_dir 规则对称）。"""
        return cls._resolve_account_media_unpublished_dir(root, account, cls.ACCOUNT_MEDIA_IMAGE_NAME)

    @classmethod
    def resolve_or_create_account_owner_dir(cls, account: Dict[str, Any]) -> Optional[Path]:
        """解析并确保账号在「账号库」下的一级素材目录存在，供资源管理器打开。

        顺序：规范路径已存在则直接用；否则若「视频/未发布」可解析且存在则取其上级账号目录；
        再否则在规范路径上创建目录树（与 sync 中单账号逻辑一致）。

        Returns:
            账号素材根目录；未配置媒体库、根路径无效或创建失败时返回 None。
        """
        root = cls.ensure_initialized()
        if root is None or not root.is_dir():
            return None

        platform_id = str(account.get("platform") or "").strip()
        work = dict(account)
        nick = (
            str(work.get("platform_username") or work.get("account_name") or "").strip()
        )
        if not nick:
            aid = work.get("id")
            nick = f"账号{aid}" if aid is not None else "未命名账号"
            work["platform_username"] = nick

        lib_root = cls.account_library_root(root)
        dir_name = cls.platform_account_folder_name(platform_id, nick)
        canonical = lib_root / dir_name

        if canonical.is_dir():
            try:
                return canonical.resolve()
            except OSError:
                return canonical

        vp = cls.resolve_account_video_unpublished_dir(root, work)
        if vp.exists():
            owner = vp.parent.parent
            if owner.is_dir():
                try:
                    return owner.resolve()
                except OSError:
                    return owner

        try:
            canonical.mkdir(parents=True, exist_ok=True)
            cls._ensure_video_image_branches(canonical)
            return canonical.resolve()
        except OSError as e:
            logger.warning(
                "创建或补齐账号素材目录失败 (path=%s): %s",
                canonical,
                e,
                exc_info=True,
            )
            return None

    @classmethod
    def account_image_unpublished_dir(cls, root: Path, account: Dict[str, Any]) -> Path:
        """某账号下「图文 / 未发布」目录。"""
        lib = cls.account_library_root(root)
        folder = cls.platform_account_folder_name(
            str(account.get("platform") or ""),
            str(
                account.get("platform_username")
                or account.get("account_name")
                or ""
            ),
        )
        return lib / folder / cls.ACCOUNT_MEDIA_IMAGE_NAME / cls.UNPUBLISHED_NAME

    @classmethod
    def group_video_unpublished_dir(cls, root: Path, group_name: str) -> Path:
        """某账号组下「视频 / 未发布」目录。"""
        lib = cls.account_library_root(root)
        gfolder = cls.account_group_material_folder_name(group_name)
        return lib / gfolder / cls.ACCOUNT_MEDIA_VIDEO_NAME / cls.UNPUBLISHED_NAME

    @classmethod
    def group_image_unpublished_dir(cls, root: Path, group_name: str) -> Path:
        """某账号组下「图文 / 未发布」目录。"""
        lib = cls.account_library_root(root)
        gfolder = cls.account_group_material_folder_name(group_name)
        return lib / gfolder / cls.ACCOUNT_MEDIA_IMAGE_NAME / cls.UNPUBLISHED_NAME

    # ---- 已发布目录（与上方「未发布」方法对称，多一层 date_str 子目录） ----

    @classmethod
    def account_video_published_dir(cls, root: Path, account: Dict[str, Any], date_str: str) -> Path:
        """某账号下「视频 / 已发布 / <date_str>」目录。"""
        lib = cls.account_library_root(root)
        folder = cls.platform_account_folder_name(
            str(account.get("platform") or ""),
            str(account.get("platform_username") or account.get("account_name") or ""),
        )
        return lib / folder / cls.ACCOUNT_MEDIA_VIDEO_NAME / cls.PUBLISHED_NAME / date_str

    @classmethod
    def account_image_published_dir(cls, root: Path, account: Dict[str, Any], date_str: str) -> Path:
        """某账号下「图文 / 已发布 / <date_str>」目录。"""
        lib = cls.account_library_root(root)
        folder = cls.platform_account_folder_name(
            str(account.get("platform") or ""),
            str(account.get("platform_username") or account.get("account_name") or ""),
        )
        return lib / folder / cls.ACCOUNT_MEDIA_IMAGE_NAME / cls.PUBLISHED_NAME / date_str

    @classmethod
    def group_video_published_dir(cls, root: Path, group_name: str, date_str: str) -> Path:
        """某账号组下「视频 / 已发布 / <date_str>」目录。"""
        lib = cls.account_library_root(root)
        gfolder = cls.account_group_material_folder_name(group_name)
        return lib / gfolder / cls.ACCOUNT_MEDIA_VIDEO_NAME / cls.PUBLISHED_NAME / date_str

    @classmethod
    def group_image_published_dir(cls, root: Path, group_name: str, date_str: str) -> Path:
        """某账号组下「图文 / 已发布 / <date_str>」目录。"""
        lib = cls.account_library_root(root)
        gfolder = cls.account_group_material_folder_name(group_name)
        return lib / gfolder / cls.ACCOUNT_MEDIA_IMAGE_NAME / cls.PUBLISHED_NAME / date_str

    @classmethod
    def _resolve_root_under_base(cls, base: Path) -> Path:
        """在基础目录下解析媒体库根文件夹（固定为 `媒小宝媒体库`）。"""
        return base / cls.ROOT_FOLDER_NAME

    @classmethod
    def _get_config_center(cls) -> ConfigCenter:
        """获取与全应用一致的 ConfigCenter（main 注册的单例）。

        正常启动时与设置页、其它服务为**同一内存对象、同一 JSON 文件**，开发/生产行为一致。
        仅单元测试或未走 main 初始化时回退到 ``ConfigCenter()``（目录已默认为用户 config 目录）。
        """
        cc = get_registered_config_center()
        if cc is not None:
            return cc
        logger.debug("ConfigCenter 未注册（多为测试场景），媒体库配置使用独立 ConfigCenter 实例。")
        return ConfigCenter()

    # ---------------- 配置读写 ----------------

    @classmethod
    def get_root_base_dir(cls) -> Optional[Path]:
        """获取用户配置的媒体库“基础目录”（未附带 `媒小宝媒体库` 子目录）。

        Returns:
            Path 或 None：当尚未配置或配置为空/无效时返回 None。
        """
        config_center = cls._get_config_center()
        app_config = config_center.get_app_config()
        raw_path = (app_config.get(cls.APP_CONFIG_FIELD) or "").strip()
        if not raw_path:
            return None
        try:
            path = Path(raw_path).expanduser()
            return path
        except Exception as e:
            logger.warning("解析媒体库基础路径失败: %s (value=%r)", e, raw_path)
            return None

    @classmethod
    def get_root_dir(cls) -> Optional[Path]:
        """获取完整的媒体库根目录（`.../媒小宝媒体库`）。未配置基础路径时返回 None。"""
        base = cls.get_root_base_dir()
        if base is None:
            return None
        return cls._resolve_root_under_base(base)

    @classmethod
    async def set_root_base_dir(cls, base_dir: Path | str) -> bool:
        """设置媒体库基础目录并持久化到 app_config 中。

        Args:
            base_dir: 用户选择的物理目录路径（不含 `媒小宝媒体库` 子目录）。

        Returns:
            bool: 是否保存成功（仅代表配置写入成功，目录初始化是否成功需单独检查）。
        """
        try:
            base_path = Path(str(base_dir)).expanduser().resolve()
        except Exception as e:
            logger.error("设置媒体库路径失败，解析路径异常: %s", e, exc_info=True)
            return False

        if not base_path.exists():
            try:
                base_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error("创建媒体库基础路径失败: %s (path=%s)", e, base_path, exc_info=True)
                return False

        config_center = cls._get_config_center()
        await config_center.initialize()
        # 浅拷贝合并，避免与其它处对 app_config 的引用互相覆盖未写入的字段
        app_config = {**config_center.get_app_config()}
        app_config[cls.APP_CONFIG_FIELD] = str(base_path)

        try:
            await config_center.update(cls.APP_CONFIG_KEY, app_config)
            logger.info("媒体库基础路径已更新为: %s", base_path)
            return True
        except Exception as e:
            logger.error("保存媒体库路径到配置失败: %s", e, exc_info=True)
            return False

    # ---------------- 目录初始化 ----------------

    @classmethod
    def _ensure_static_directories(cls, root: Path) -> None:
        """创建媒小宝媒体库静态骨架：视频库、图片库、账号库（各账号/组子目录由 sync 补齐）。"""
        video_dir = root / cls.VIDEO_FOLDER_NAME
        image_dir = root / cls.IMAGE_FOLDER_NAME
        account_lib = cls.account_library_root(root)

        root.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)
        account_lib.mkdir(parents=True, exist_ok=True)

    @classmethod
    def ensure_initialized(cls) -> Optional[Path]:
        """确保媒体库目录结构已初始化。

        会在当前配置的基础路径下创建：
            媒小宝媒体库/
                视频库/
                图片库/
                账号库/            # 空壳；其下账号/账号组文件夹由 sync 创建

        Returns:
            Path 或 None：成功时返回根目录路径，未配置或失败时返回 None。
        """
        base = cls.get_root_base_dir()
        if base is None:
            logger.debug("尚未配置媒体库基础路径，跳过初始化。")
            return None

        try:
            root = cls._resolve_root_under_base(base)
            cls._ensure_static_directories(root)
            logger.debug("媒体库基础目录已初始化: %s", root)
            return root
        except PermissionError as e:
            logger.error("初始化媒体库目录失败：权限不足 (%s)", e, exc_info=True)
            return None
        except OSError as e:
            logger.error("初始化媒体库目录失败：OS 错误 (%s)", e, exc_info=True)
            return None
        except Exception as e:
            logger.error("初始化媒体库目录失败：未知异常 (%s)", e, exc_info=True)
            return None

    # 与「视频库」页面、批量发布「从媒体库选择」共用：可扩展名与批量页 SUPPORTED_VIDEO_EXTENSIONS 对齐
    VIDEO_PICKER_EXTENSIONS = {
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".flv",
        ".wmv",
        ".m4v",
        ".webm",
    }

    @classmethod
    def list_video_entries_for_picker(cls) -> List[Dict[str, Any]]:
        """扫描当前配置媒体库中的视频文件（视频库根目录 + 各账号/组「视频/未发布」）。

        返回字典含 file_path、file_name、original_name、file_size、owner_label，
        供批量发布等弹窗多选；数据源与 UI「媒体库 - 视频库」一致。
        """
        root = cls.ensure_initialized()
        if root is None:
            return []

        video_dir = root / cls.VIDEO_FOLDER_NAME
        account_lib = cls.account_library_root(root)
        out: List[Dict[str, Any]] = []

        def append_dir(target_dir: Path, owner_label: str) -> None:
            if not target_dir.exists():
                return
            try:
                for entry in os.scandir(str(target_dir)):
                    if not entry.is_file():
                        continue
                    suffix = os.path.splitext(entry.name)[1].lower()
                    if suffix not in cls.VIDEO_PICKER_EXTENSIONS:
                        continue
                    fp = os.path.abspath(entry.path)
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    out.append(
                        {
                            "file_path": fp,
                            "file_name": entry.name,
                            "original_name": entry.name,
                            "file_size": size,
                            "owner_label": owner_label,
                        }
                    )
            except OSError as e:
                logger.warning("扫描视频目录失败 (%s): %s", target_dir, e)

        append_dir(video_dir, "未分配")

        if account_lib.exists():
            try:
                for entry in os.scandir(str(account_lib)):
                    if not entry.is_dir():
                        continue
                    owner = cls.owner_label_for_account_library_entry(entry.name)
                    unpublished_dir = (
                        Path(entry.path)
                        / cls.ACCOUNT_MEDIA_VIDEO_NAME
                        / cls.UNPUBLISHED_NAME
                    )
                    append_dir(unpublished_dir, owner)
            except OSError as e:
                logger.warning("扫描账号库失败 (%s): %s", account_lib, e)

        out.sort(key=lambda x: str(x.get("file_path") or "").lower())
        return out

    @classmethod
    def list_video_entries_for_accounts(
        cls,
        accounts: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """只扫描指定账号/账号组「视频/未发布」目录中的视频文件。

        不含公共「视频库」，不含已发布目录。
        供批量视频页面「从媒体库选择」使用，仅展示已添加账号的素材。

        Args:
            accounts: 账号 dict 列表（含 platform / platform_username / _type / group_name 等）

        Returns:
            视频文件字典列表（同 list_video_entries_for_picker 格式）
        """
        root = cls.ensure_initialized()
        if root is None:
            return []

        out: List[Dict[str, Any]] = []

        def append_dir(target_dir: Path, owner_label: str) -> None:
            if not target_dir.exists():
                return
            try:
                for entry in os.scandir(str(target_dir)):
                    if not entry.is_file():
                        continue
                    suffix = os.path.splitext(entry.name)[1].lower()
                    if suffix not in cls.VIDEO_PICKER_EXTENSIONS:
                        continue
                    fp = os.path.abspath(entry.path)
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    out.append(
                        {
                            "file_path": fp,
                            "file_name": entry.name,
                            "original_name": entry.name,
                            "file_size": size,
                            "owner_label": owner_label,
                        }
                    )
            except OSError as e:
                logger.warning("扫描视频目录失败 (%s): %s", target_dir, e)

        for acc in accounts:
            if acc.get("_type") == "group":
                group_name = (acc.get("group_name") or "").strip()
                if not group_name:
                    continue
                scan_dir = cls.group_video_unpublished_dir(root, group_name)
                label = cls.owner_label_for_group_material_folder(
                    cls.account_group_material_folder_name(group_name)
                )
                append_dir(scan_dir, label)
            else:
                scan_dir = cls.resolve_account_video_unpublished_dir(root, acc)
                try:
                    folder_name = scan_dir.parent.parent.name
                except (IndexError, AttributeError):
                    folder_name = cls.platform_account_folder_name(
                        str(acc.get("platform") or ""),
                        str(acc.get("platform_username") or acc.get("account_name") or ""),
                    )
                append_dir(scan_dir, cls.owner_label_for_account_library_entry(folder_name))

        out.sort(key=lambda x: str(x.get("file_path") or "").lower())
        return out

    @classmethod
    async def initialize_and_sync(cls) -> Optional[Path]:
        """初始化静态目录后，立即根据数据库同步「账号库」下账号与账号组文件夹。"""
        root = cls.ensure_initialized()
        if root is None:
            return None
        await cls.sync_platform_account_tree()
        return root

    # ---------------- 账号库目录同步（账号 + 账号组） ----------------

    @classmethod
    async def sync_platform_account_tree(cls) -> None:
        """根据数据库中的平台账号与账号组，在「账号库」下创建一级文件夹，并补齐 视频/图文 × 已发布/未发布。

        规则：
        - 根路径：.../媒小宝媒体库/账号库
        - 一级子目录：单账号为「平台中文名_昵称」；账号组为「账号组_<组名>」（与单账号并列，无中间「账号组」父目录）
        - 每个一级目录下：`视频/{已发布,未发布}`、`图文/{已发布,未发布}`
        """
        root = cls.ensure_initialized()
        if root is None:
            return

        lib_root = cls.account_library_root(root)

        # 读取账号列表（支持单用户模式：user_id 可为 None）
        try:
            repo = AccountRepositoryAsync()
            accounts: List[Dict[str, Any]] = await repo.find_all(user_id=None, platform=None)
        except Exception as e:
            logger.error("同步媒体库账号目录失败：读取账号列表异常 (%s)", e, exc_info=True)
            return

        if not accounts:
            logger.debug("当前无平台账号记录，跳过按账号创建子目录。")

        for acc in accounts:
            platform_id = str(acc.get("platform") or "").strip()
            if not platform_id:
                logger.debug(
                    "跳过无平台字段的账号记录（id=%s），不创建媒体库目录。",
                    acc.get("id"),
                )
                continue
            nickname = (acc.get("platform_username") or acc.get("account_name") or "").strip()
            if not nickname:
                aid = acc.get("id")
                nickname = f"账号{aid}" if aid is not None else "未命名账号"
            dir_name = cls.platform_account_folder_name(platform_id, nickname)
            account_dir = lib_root / dir_name
            try:
                cls._ensure_video_image_branches(account_dir)
            except PermissionError as e:
                logger.warning(
                    "创建账号素材目录失败：权限不足 (account=%s, error=%s)",
                    dir_name,
                    e,
                    exc_info=True,
                )
            except OSError as e:
                logger.warning(
                    "创建账号素材目录失败：OS 错误 (account=%s, error=%s)",
                    dir_name,
                    e,
                    exc_info=True,
                )
            except Exception as e:
                logger.warning(
                    "创建账号素材目录失败：未知异常 (account=%s, error=%s)",
                    dir_name,
                    e,
                    exc_info=True,
                )

        # 账号组：与账号并列，直接位于「账号库」下
        n_groups = 0
        try:
            from src.domain.repositories.account_group_repository_async import (
                AccountGroupRepositoryAsync,
            )

            group_repo = AccountGroupRepositoryAsync()
            groups: List[Dict[str, Any]] = await group_repo.find_all(user_id=None)
            n_groups = sum(1 for g in groups if (g.get("group_name") or "").strip())

            for group in groups:
                group_name = (group.get("group_name") or "").strip()
                if not group_name:
                    continue
                try:
                    group_dir = lib_root / cls.account_group_material_folder_name(group_name)
                    cls._ensure_video_image_branches(group_dir)
                except Exception as e:
                    logger.warning(
                        "创建账号组素材目录失败 (group=%s, error=%s)",
                        group_name,
                        e,
                        exc_info=True,
                    )
        except Exception as e:
            logger.warning("同步媒体库账号组目录失败: %s", e, exc_info=True)

        logger.info(
            "媒体库目录同步完成：处理账号记录 %d 条，有效账号组 %d 个。",
            len(accounts),
            n_groups,
        )

    @classmethod
    def rename_platform_account_folder(
        cls,
        platform_id: str,
        old_platform_username: str,
        new_platform_username: str,
    ) -> bool:
        """账号昵称变更时重命名账号素材目录；目标已存在时不覆盖。"""
        root = cls.ensure_initialized()
        if root is None:
            return False
        lib_root = cls.account_library_root(root)
        old_dir = lib_root / cls.platform_account_folder_name(platform_id, old_platform_username)
        new_dir = lib_root / cls.platform_account_folder_name(platform_id, new_platform_username)
        if not old_dir.exists() or old_dir == new_dir:
            return False
        if new_dir.exists():
            logger.warning("昵称目录重命名跳过：目标目录已存在 old=%s new=%s", old_dir, new_dir)
            return False
        try:
            old_dir.rename(new_dir)
            logger.info("账号素材目录已重命名: %s -> %s", old_dir, new_dir)
            return True
        except Exception as e:
            logger.warning("账号素材目录重命名失败: %s", e, exc_info=True)
            return False

