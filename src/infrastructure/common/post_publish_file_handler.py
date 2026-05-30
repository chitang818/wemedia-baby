"""
发布后文件操作处理器
文件路径：src/infrastructure/common/post_publish_file_handler.py
功能：在发布列表任务发布成功后，对发布的视频/图文文件执行移动或删除操作。

核心逻辑（重构后）：
- task_source == "account"（或旧数据 None）：任务成功后立即移到该账号的已发布文件夹；
- task_source == "group"：任务成功后，查询数据库中是否还有其他任务在引用同一文件；
  - 若有其他任务仍在引用：不移动，等待或保留；
  - 若当前是最后一个引用该文件的任务：移到账号组的已发布文件夹。
- 旧数据（task_source is None）降级为原逻辑（独立账号分组）。
"""

from __future__ import annotations

import logging
import os
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# 账号组共用同一文件时：仅这些状态的记录仍可能依赖「未发布」路径下的源文件，应阻塞移动。
# success 在文件移动前仍保留旧 file_path，若与「非 deleted 全表」一起判断会误判为永久有引用。
_STATUSES_BLOCKING_SHARED_FILE_MOVE = frozenset({"pending", "running", "failed"})


@dataclass
class FileGroupInfo:
    """单个「文件 + 作用域」分组的完整信息。"""
    # 该任务组涉及的实际文件路径（图文可能多个，从 file_path 逗号分隔而来）
    file_paths: List[str]
    # 分组内所有任务 ID
    task_ids: Set[int] = field(default_factory=set)
    # 尚未完成（成功/失败）的任务 ID 集合，初始等于 task_ids
    pending_task_ids: Set[int] = field(default_factory=set)
    # 分组内是否已有任务失败
    has_failed: bool = False
    # "account" 或 "group"
    target_type: str = "account"
    # account 类型时使用（构造路径需要 platform + platform_username）
    platform: str = ""
    platform_username: str = ""
    # group 类型时使用
    group_name: str = ""
    # "video" 或 "image"
    file_type: str = "video"
    # 图文任务且图片来源为文件夹时，存储文件夹的绝对路径（来自 __FOLDER__: 标记）；
    # 普通散图或视频任务时为空字符串。
    source_folder: str = ""


class PostPublishFileHandler:
    """发布后文件操作处理器（全静态方法，无需实例化）。"""

    # ------------------------------------------------------------------ #
    # 公开接口                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def build_file_groups(
        pending_tasks: List[Dict[str, Any]],
        account_repo: Any,
        group_repo: Any,
    ) -> Dict[str, FileGroupInfo]:
        """
        在发布队列启动时调用，对所有 pending 任务预分析，建立文件引用分组表。

        新逻辑：
        - task_source == "account"（或 None 旧数据）：每个任务独立分组，移到账号已发布文件夹；
        - task_source == "group"：同一 (file_path, group_id) 共享分组，等所有相关任务处理后
          移到账号组已发布文件夹（由 on_task_success 动态查库判断最后引用）。

        Args:
            pending_tasks: 待发布任务列表（publish_record dict 格式）
            account_repo:  AccountRepositoryAsync 实例（用于查询 group_id）
            group_repo:    AccountGroupRepositoryAsync 实例（用于查询 group_name）

        Returns:
            key 为 "{normalized_file_path}|{scope_key}" 的分组字典
        """
        if not pending_tasks:
            return {}

        # 为每条任务解析 group_id（仅 group 任务需要）
        task_meta: List[Dict[str, Any]] = []
        for task in pending_tasks:
            task_source = task.get("task_source")
            acc_id = task.get("platform_account_id")
            group_id: Optional[int] = None
            group_name: str = ""

            if task_source == "group" and acc_id:
                try:
                    acc = await account_repo.find_by_id(int(acc_id))
                    if acc:
                        group_id = acc.get("group_id") or None
                except Exception as e:
                    logger.warning("查询账号 group_id 失败 (account_id=%s): %s", acc_id, e)
            elif task_source is None and acc_id:
                # 旧数据降级：仍按原逻辑查询 group_id
                try:
                    acc = await account_repo.find_by_id(int(acc_id))
                    if acc:
                        group_id = acc.get("group_id") or None
                except Exception as e:
                    logger.warning("查询账号 group_id 失败 (account_id=%s): %s", acc_id, e)

            task_meta.append({
                "task": task,
                "task_source": task_source,
                "group_id": group_id,
                "group_name": group_name,
            })

        # 旧数据（task_source=None）：统计 (file_path, group_id) 出现次数，≥2 认为是组共用
        count_map: Counter = Counter()
        for m in task_meta:
            if m["task_source"] is None:
                task = m["task"]
                fp_norm = PostPublishFileHandler._normalize_file_path(task.get("file_path") or "")
                gid = m["group_id"]
                if gid:
                    count_map[(fp_norm, gid)] += 1

        # 补全 group_name
        group_name_cache: Dict[int, str] = {}
        for m in task_meta:
            gid = m["group_id"]
            if gid and gid not in group_name_cache:
                try:
                    grp = await group_repo.find_by_id(int(gid))
                    group_name_cache[gid] = (grp.get("name") or grp.get("group_name") or "") if grp else ""
                except Exception as e:
                    logger.warning("查询账号组名称失败 (group_id=%s): %s", gid, e)
                    group_name_cache[gid] = ""
            if gid:
                m["group_name"] = group_name_cache.get(gid, "")

        # 构建分组
        file_groups: Dict[str, FileGroupInfo] = {}

        for m in task_meta:
            task = m["task"]
            task_source = m["task_source"]
            gid = m["group_id"]
            fp_raw = task.get("file_path") or ""
            fp_norm = PostPublishFileHandler._normalize_file_path(fp_raw)
            task_id = task.get("id")

            if task_source == "account":
                # 新数据-账号：每个任务独立分组，立即移到账号已发布文件夹
                acc_id = task.get("platform_account_id") or task.get("id") or id(task)
                scope_key = f"account:{acc_id}"
                target_type = "account"
                group_name = ""
            elif task_source == "group":
                # 新数据-账号组：同一 (fp, gid) 共享分组；移动逻辑在 on_task_success 中按需查库
                scope_key = f"group:{gid}" if gid else f"account:{task.get('platform_account_id') or id(task)}"
                target_type = "group" if gid else "account"
                group_name = m.get("group_name") or ""
            else:
                # 旧数据降级：按原逻辑
                is_group_shared = bool(gid and count_map.get((fp_norm, gid), 0) >= 2)
                if is_group_shared:
                    scope_key = f"group:{gid}"
                    target_type = "group"
                    group_name = m.get("group_name") or ""
                else:
                    acc_id = task.get("platform_account_id") or task.get("id") or id(task)
                    scope_key = f"account:{acc_id}"
                    target_type = "account"
                    group_name = ""

            group_key = f"{fp_norm}|{scope_key}"
            file_type = PostPublishFileHandler._detect_file_type(fp_raw)

            if group_key not in file_groups:
                file_groups[group_key] = FileGroupInfo(
                    file_paths=PostPublishFileHandler._split_file_paths(fp_raw),
                    task_ids=set(),
                    pending_task_ids=set(),
                    has_failed=False,
                    target_type=target_type,
                    platform=str(task.get("platform") or ""),
                    platform_username=str(task.get("platform_username") or ""),
                    group_name=group_name,
                    file_type=file_type,
                    # 解析 __FOLDER__: 标记，填充文件夹来源路径
                    source_folder=PostPublishFileHandler._extract_folder_path(fp_raw),
                )
            if task_id is not None:
                file_groups[group_key].task_ids.add(task_id)
                file_groups[group_key].pending_task_ids.add(task_id)

        return file_groups

    @staticmethod
    async def on_task_success(
        task_id: int,
        task: Dict[str, Any],
        file_groups: Dict[str, FileGroupInfo],
        action: str,
        user_log: logging.Logger,
        publish_repo: Any = None,
    ) -> None:
        """
        某条任务发布成功后调用。

        - task_source == "account"（或旧数据）：若分组内所有任务均已成功，立即移到账号已发布文件夹。
        - task_source == "group"：查询数据库中是否还有其他任务引用同一文件（排除自身）；
          无其他引用时移到账号组已发布文件夹。

        Args:
            task_id:      已成功的任务 ID
            task:         该任务的 publish_record 字典
            file_groups:  build_file_groups 构建的分组表
            action:       "move" 或 "delete"
            user_log:     用于向发布日志框输出的 Logger
            publish_repo: PublishRecordRepositoryAsync 实例（group 任务需要查库）
        """
        task_source = task.get("task_source")

        if task_source == "group":
            # 新逻辑：group 任务直接查库判断是否还有其他任务引用同一文件
            await PostPublishFileHandler._handle_group_task_success(
                task_id, task, action, user_log, publish_repo
            )
            # 同步更新 file_groups 状态（供 on_task_failed 感知）
            groups = PostPublishFileHandler._find_groups_for_task(task_id, file_groups)
            for _, info in groups:
                info.pending_task_ids.discard(task_id)
        else:
            # account 任务（或旧数据 None）：沿用原分组逻辑
            groups = PostPublishFileHandler._find_groups_for_task(task_id, file_groups)
            for group_key, info in groups:
                info.pending_task_ids.discard(task_id)
                if info.has_failed:
                    continue
                if info.pending_task_ids:
                    fps = ", ".join(os.path.basename(p) for p in info.file_paths)
                    user_log.info(f"[文件整理] ⏳ {fps} 还有其他任务未完成，暂不处理")
                else:
                    path_results = await PostPublishFileHandler._execute_file_action(info, action, user_log)
                    await PostPublishFileHandler._update_file_path_in_db(
                        task_id, task.get("file_path") or "", path_results, publish_repo, user_log
                    )

    @staticmethod
    def on_task_failed(
        task_id: int,
        file_groups: Dict[str, FileGroupInfo],
    ) -> None:
        """
        某条任务发布失败时调用，标记分组 has_failed=True，阻止该组后续文件操作。
        """
        groups = PostPublishFileHandler._find_groups_for_task(task_id, file_groups)
        for _, info in groups:
            info.pending_task_ids.discard(task_id)
            info.has_failed = True

    @staticmethod
    def on_task_reset_to_pending(
        task_id: int,
        file_groups: Dict[str, FileGroupInfo],
    ) -> None:
        """任务被复位为待发布时调用，清理失败标记，避免后续成功后文件处理被阻断。"""
        groups = PostPublishFileHandler._find_groups_for_task(task_id, file_groups)
        for _, info in groups:
            info.has_failed = False
            info.pending_task_ids.add(task_id)

    # ------------------------------------------------------------------ #
    # 内部方法                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _handle_group_task_success(
        task_id: int,
        task: Dict[str, Any],
        action: str,
        user_log: logging.Logger,
        publish_repo: Any,
    ) -> None:
        """处理 task_source == "group" 任务的发布成功后文件操作。"""
        file_path_raw = task.get("file_path") or ""
        if not file_path_raw.strip():
            return

        # 查询数据库中是否还有其他任务使用同一文件（排除当前任务 ID）
        other_tasks_exist = await PostPublishFileHandler._check_other_tasks_using_file(
            file_path_raw, exclude_task_id=task_id, publish_repo=publish_repo
        )

        file_paths = PostPublishFileHandler._split_file_paths(file_path_raw)
        fnames = ", ".join(os.path.basename(p) for p in file_paths)

        if other_tasks_exist:
            user_log.info(f"[文件整理] ⏳ {fnames} 还被其他任务引用，暂不处理")
            return

        # 无其他任务引用，构建 FileGroupInfo 并执行文件操作
        # 优先通过数据库链路查账号组名（账号 group_id → 账号组名）
        group_name = await PostPublishFileHandler._resolve_group_name_for_task(task, publish_repo)

        # 数据库链路查不到时，尝试从文件路径推断账号组名
        # 场景：账号的 group_id 为空/账号组被删除/ServiceLocator 未注册仓储等
        if not group_name and file_paths:
            inferred = PostPublishFileHandler._resolve_group_name_from_file_path(file_paths[0])
            if inferred:
                logger.info(
                    "[文件整理] 数据库查不到账号组名，从文件路径推断组名: %r (task_id=%s)",
                    inferred,
                    task_id,
                )
                group_name = inferred

        file_type = PostPublishFileHandler._detect_file_type(file_path_raw)

        info = FileGroupInfo(
            file_paths=file_paths,
            target_type="group" if group_name else "account",
            platform=str(task.get("platform") or ""),
            platform_username=str(task.get("platform_username") or ""),
            group_name=group_name,
            file_type=file_type,
            # 解析 __FOLDER__: 标记，填充文件夹来源路径
            source_folder=PostPublishFileHandler._extract_folder_path(file_path_raw),
        )
        path_results = await PostPublishFileHandler._execute_file_action(info, action, user_log)
        # 更新所有引用该文件的任务（包括当前任务和之前已成功的同组任务）
        await PostPublishFileHandler._update_file_path_for_all_referencing_tasks(
            file_path_raw, path_results, publish_repo, user_log
        )

    @staticmethod
    async def _check_other_tasks_using_file(
        file_path_raw: str,
        exclude_task_id: int,
        publish_repo: Any,
    ) -> bool:
        """
        查询数据库中是否还有除 exclude_task_id 之外的其他任务在引用同一文件。
        返回 True 表示还有其他任务引用（不应移动文件）。

        仅统计 pending/running/failed：已成功任务在移动完成前仍带旧路径，不得计入阻塞。
        """
        if publish_repo is None:
            return False
        try:
            from src.infrastructure.storage.orm_models.publish_record import PublishRecord
            fp_norm = PostPublishFileHandler._normalize_file_path(file_path_raw)
            blocking = list(_STATUSES_BLOCKING_SHARED_FILE_MOVE)
            all_records = await PublishRecord.filter(
                status__in=blocking
            ).exclude(id=exclude_task_id).values("id", "file_path")

            for rec in all_records:
                rec_fp_norm = PostPublishFileHandler._normalize_file_path(rec.get("file_path") or "")
                if rec_fp_norm == fp_norm:
                    return True
            return False
        except Exception as e:
            logger.warning("查询其他任务文件引用失败 (task_id=%s): %s", exclude_task_id, e)
            return False

    @staticmethod
    async def _resolve_group_name_for_task(
        task: Dict[str, Any],
        publish_repo: Any,
    ) -> str:
        """
        根据任务信息查询账号所属组名。

        查询优先级（高道优先）：
        1. 直接从 task['group_id'] 读取（未来数据库增强后使用）
        2. 通过 platform_account_id 关联查询账号组名（当前主路）
        """
        try:
            from src.infrastructure.storage.orm_models.platform_account import PlatformAccount
            from src.infrastructure.storage.orm_models.account_group import AccountGroup as AccountGroupORM

            # --- 方案一：直接从 task['group_id'] 读取（数据库字段增强后走此路） ---
            direct_gid = task.get("group_id")
            if direct_gid:
                try:
                    grp = await AccountGroupORM.get_or_none(id=int(direct_gid))
                    if grp:
                        return grp.group_name or ""
                except Exception:
                    pass

            # --- 方案二：通过 platform_account_id 关联查询（主要路径） ---
            acc_id = task.get("platform_account_id")
            if not acc_id:
                return ""

            # 直接用 Tortoise ORM select_related 一次性拿到账号及其关联组
            # （与 _attach_account_group_names 的做法一致，不再依赖 ServiceLocator）
            account = await PlatformAccount.get_or_none(id=int(acc_id))
            if account is None:
                return ""

            group_id = getattr(account, "group_id", None)
            if not group_id:
                logger.debug(
                    "_resolve_group_name_for_task: 账号 %s 的 group_id 为空（该账号未关联到任何组）",
                    acc_id,
                )
                return ""

            grp = await AccountGroupORM.get_or_none(id=int(group_id))
            if grp:
                return grp.group_name or ""

        except Exception as e:
            logger.warning("查询账号组名称失败 (task_id=%s): %s", task.get("id"), e)
        return ""

    @staticmethod
    def _resolve_group_name_from_file_path(file_path: str) -> str:
        """
        从文件路径中推断账号组名。

        原理：文件路径格式为 `.../账号库/账号组_<组名>/视频/未发布/xxx.mp4`，
        提取相对于「账号库」目录的第一层子目录名，若以 `账号组_` 开头则返回后面的组名。

        用于数据库链路无法获取组名时的兜底，确保文件移动到正确目录。
        """
        try:
            from src.infrastructure.common.material_library_manager import MaterialLibraryManager

            root = MaterialLibraryManager.get_root_dir()
            if root is None:
                return ""

            account_lib = MaterialLibraryManager.account_library_root(root)
            prefix = MaterialLibraryManager.GROUP_MATERIAL_PREFIX  # "账号组_"

            # 将文件路径与账号库路径对齐，提取第一层子目录名
            try:
                fp = Path(file_path).resolve()
                lib_resolved = account_lib.resolve()
                # 计算相对路径：fp 相对于账号库根目录
                rel = fp.relative_to(lib_resolved)
                # 取第一层目录名（parts[0]）
                first_part = rel.parts[0] if rel.parts else ""
            except (ValueError, IndexError):
                # file_path 不在账号库下，尝试字符串匹配
                fp_str = file_path.replace("\\", "/")
                lib_str = str(account_lib).replace("\\", "/").rstrip("/")
                if lib_str not in fp_str:
                    return ""
                after_lib = fp_str[fp_str.index(lib_str) + len(lib_str):].lstrip("/")
                first_part = after_lib.split("/")[0] if after_lib else ""

            # 检查是否为账号组目录（以 `账号组_` 开头）
            if first_part and first_part.startswith(prefix):
                group_name = first_part[len(prefix):]
                return group_name
        except Exception as e:
            logger.debug("从文件路径推断账号组名失败 (file=%r): %s", file_path, e)
        return ""

    @staticmethod
    def _find_groups_for_task(
        task_id: int,
        file_groups: Dict[str, FileGroupInfo],
    ) -> List[tuple]:
        """返回 task_id 所属的所有 (group_key, FileGroupInfo) 对。"""
        return [
            (k, v) for k, v in file_groups.items()
            if task_id in v.task_ids
        ]

    @staticmethod
    async def _update_file_path_in_db(
        task_id: int,
        original_file_path: str,
        path_results: Dict[str, Optional[str]],
        publish_repo: Any,
        user_log: logging.Logger,
    ) -> None:
        """根据文件操作结果，将新的 file_path 写回数据库。

        - 移动成功：对应路径替换为新路径
        - 删除成功：对应路径替换为 "__DELETED__"
        - 操作失败（None）：保留原路径不变

        支持文件夹来源场景：__FOLDER__:xxx 条目和各图片路径均会一并替换。
        """
        if publish_repo is None or not path_results:
            return

        prefix = PostPublishFileHandler._FOLDER_MARKER_PREFIX

        # 保留 file_path 的所有条目（含 __FOLDER__: 标记），不过滤
        original_parts = [
            p.strip() for p in original_file_path.split(",") if p.strip()
        ]
        new_parts: List[str] = []
        changed = False

        for orig in original_parts:
            orig_key = orig.strip()
            result = path_results.get(orig_key)
            if result is None:
                # 操作失败或未处理，保留原条目
                new_parts.append(orig_key)
            else:
                new_parts.append(result)
                changed = True

        # 补充 path_results 中有但上面未匹配到的（路径大小写/normalize 差异）
        if not changed:
            norm_map: Dict[str, str] = {}
            for k, v in path_results.items():
                if v is not None:
                    # __FOLDER__: 条目不做路径 normcase（含前缀），只对纯路径部分做
                    if k.startswith(prefix):
                        norm_map[k.lower()] = v
                    else:
                        norm_map[os.path.normcase(os.path.normpath(k))] = v
            new_parts_retry: List[str] = []
            for orig in original_parts:
                if orig.startswith(prefix):
                    result = norm_map.get(orig.lower())
                else:
                    result = norm_map.get(os.path.normcase(os.path.normpath(orig)))
                if result is not None:
                    new_parts_retry.append(result)
                    changed = True
                else:
                    new_parts_retry.append(orig)
            if changed:
                new_parts = new_parts_retry

        if not changed:
            return

        new_file_path = ",".join(new_parts)
        try:
            await publish_repo.update_content(task_id, file_path=new_file_path)
            user_log.debug(f"[文件整理] 已更新任务 {task_id} 的文件路径记录")
        except Exception as e:
            user_log.warning(f"[文件整理] ⚠️ 更新文件路径失败（不影响发布结果）：{e}")
            logger.error("更新 file_path 失败 task_id=%s: %s", task_id, e, exc_info=True)

    @staticmethod
    async def _update_file_path_for_all_referencing_tasks(
        original_file_path: str,
        path_results: Dict[str, Optional[str]],
        publish_repo: Any,
        user_log: logging.Logger,
    ) -> None:
        """为所有引用同一文件的任务批量更新 file_path（用于组任务场景）。

        当组任务中最后一个任务触发文件移动/删除后，之前已成功的同组任务
        的 file_path 仍然是旧路径，需要一并更新。
        """
        if publish_repo is None or not path_results:
            return

        # 检查是否有实际变更
        has_any_result = any(v is not None for v in path_results.values())
        if not has_any_result:
            return

        try:
            from src.infrastructure.storage.orm_models.publish_record import PublishRecord
            fp_norm = PostPublishFileHandler._normalize_file_path(original_file_path)

            all_records = await PublishRecord.filter(
                status__not_in=["deleted_pending", "deleted_success"]
            ).values("id", "file_path")

            for rec in all_records:
                rec_fp = rec.get("file_path") or ""
                if not rec_fp:
                    continue
                if PostPublishFileHandler._normalize_file_path(rec_fp) != fp_norm:
                    continue
                task_id = rec.get("id")
                if task_id is None:
                    continue
                await PostPublishFileHandler._update_file_path_in_db(
                    task_id, rec_fp, path_results, publish_repo, user_log
                )
        except Exception as e:
            user_log.warning(f"[文件整理] ⚠️ 批量更新文件路径失败（不影响发布结果）：{e}")
            logger.error("批量更新 file_path 失败: %s", e, exc_info=True)

    @staticmethod
    async def _execute_file_action(
        info: FileGroupInfo,
        action: str,
        user_log: logging.Logger,
    ) -> Dict[str, Optional[str]]:
        """对分组内所有文件执行移动或删除操作。

        当任务图片来源为文件夹（info.source_folder 非空）时，整体移动/删除文件夹；
        否则按原有逻辑逐一移动/删除散图文件。

        Returns:
            {原始路径字符串: 结果路径字符串}
            - 移动成功：值为新路径字符串
            - 删除成功：值为 "__DELETED__"
            - 操作失败或跳过：值为 None（保留原路径，不更新数据库）
        """
        import asyncio as _asyncio
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager

        date_str = datetime.now().strftime("%Y%m%d")
        path_results: Dict[str, Optional[str]] = {}
        prefix = PostPublishFileHandler._FOLDER_MARKER_PREFIX

        # ── 图片文件夹来源：整体移动或删除整个文件夹 ──────────────────────
        if info.source_folder:
            src_folder = Path(info.source_folder).resolve()
            # 构造 __FOLDER__: 条目的原始键（与 file_path 字段中的格式保持一致）
            folder_marker_key = f"{prefix}{info.source_folder}"

            if action == "delete":
                # 删除整个文件夹目录
                ok = await _asyncio.to_thread(
                    PostPublishFileHandler._do_delete_folder, src_folder, user_log
                )
                result_val = "__DELETED__" if ok else None
                # 文件夹标记条目
                path_results[folder_marker_key] = result_val
                # 所有图片路径条目
                for p in info.file_paths:
                    path_results[p.strip()] = result_val
                return path_results

            # action == "move"
            root = MaterialLibraryManager.get_root_dir()
            if root is None:
                user_log.warning("[文件整理] ⚠️ 未配置媒体库路径，跳过移动操作")
                path_results[folder_marker_key] = None
                for p in info.file_paths:
                    path_results[p.strip()] = None
                return path_results

            try:
                target_dir = PostPublishFileHandler._resolve_target_dir(root, info, date_str)
            except Exception as e:
                user_log.warning(f"[文件整理] ⚠️ 解析目标目录失败，跳过（{e}）")
                path_results[folder_marker_key] = None
                for p in info.file_paths:
                    path_results[p.strip()] = None
                return path_results

            # 整体移动文件夹
            new_folder = await _asyncio.to_thread(
                PostPublishFileHandler._do_move_folder, src_folder, target_dir, user_log
            )
            if new_folder is None:
                # 移动失败：所有条目标记为 None（不更新数据库）
                path_results[folder_marker_key] = None
                for p in info.file_paths:
                    path_results[p.strip()] = None
            else:
                # 移动成功：更新 __FOLDER__: 条目 → 新文件夹路径
                path_results[folder_marker_key] = f"{prefix}{new_folder}"
                # 更新各图片路径 → 新文件夹路径/原文件名
                for p in info.file_paths:
                    p = p.strip()
                    if not p:
                        continue
                    img_name = Path(p).name
                    path_results[p] = str(new_folder / img_name)
            return path_results

        # ── 普通散图或视频：逐一移动/删除（原有逻辑） ─────────────────────
        for src_path_str in info.file_paths:
            src_path_str = src_path_str.strip()
            if not src_path_str:
                continue

            src = Path(src_path_str).resolve()
            basename = src.name

            if action == "delete":
                ok = await _asyncio.to_thread(PostPublishFileHandler._do_delete, src, basename, user_log)
                path_results[src_path_str] = "__DELETED__" if ok else None
                continue

            # action == "move"
            root = MaterialLibraryManager.get_root_dir()
            if root is None:
                user_log.warning("[文件整理] ⚠️ 未配置媒体库路径，跳过移动操作")
                path_results[src_path_str] = None
                continue

            try:
                target_dir = PostPublishFileHandler._resolve_target_dir(
                    root, info, date_str
                )
            except Exception as e:
                user_log.warning(f"[文件整理] ⚠️ 解析目标目录失败，跳过（{e}）")
                path_results[src_path_str] = None
                continue

            new_path = await _asyncio.to_thread(
                PostPublishFileHandler._do_move, src, target_dir, basename, user_log
            )
            path_results[src_path_str] = str(new_path) if new_path else None

        return path_results

    @staticmethod
    def _resolve_target_dir(
        root: Path,
        info: FileGroupInfo,
        date_str: str,
    ) -> Path:
        """根据 FileGroupInfo 确定目标「已发布」日期目录。"""
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager

        if info.target_type == "group":
            if info.file_type == "image":
                return MaterialLibraryManager.group_image_published_dir(root, info.group_name, date_str)
            return MaterialLibraryManager.group_video_published_dir(root, info.group_name, date_str)
        else:
            account = {"platform": info.platform, "platform_username": info.platform_username}
            if info.file_type == "image":
                return MaterialLibraryManager.account_image_published_dir(root, account, date_str)
            return MaterialLibraryManager.account_video_published_dir(root, account, date_str)

    @staticmethod
    def _do_move_folder(
        src_folder: Path,
        target_dir: Path,
        user_log: logging.Logger,
    ) -> Optional[Path]:
        """将图片文件夹整体移动到 target_dir 下，保持文件夹名，重名自动追加序号。

        内部复用 media_library_assign.move_folder_to_assign_target() 的实现逻辑，
        并额外记录用户日志。返回实际落地的文件夹 Path，失败时返回 None。
        """
        if not src_folder.exists() or not src_folder.is_dir():
            user_log.warning(f"[文件整理] ⚠️ 源文件夹不存在或不是目录，跳过移动：{src_folder}")
            return None
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            # 目标文件夹路径；同名时追加序号（与 move_folder_to_assign_target 逻辑一致）
            dst = target_dir / src_folder.name
            if dst.exists():
                stem = src_folder.name
                idx = 1
                while True:
                    candidate = target_dir / f"{stem} ({idx})"
                    if not candidate.exists():
                        dst = candidate
                        break
                    idx += 1
            shutil.move(str(src_folder), str(dst))
            user_log.info(f"[文件整理] ✅ 已将文件夹 {src_folder.name} 整体移动至 {target_dir}/")
            # 异步刷新媒体库统计（非关键路径，失败不影响主流程）
            try:
                from src.services.material.media_library_stats_service import get_media_library_stats_service
                from src.ui.utils.async_helper import run_async_from_ui
                svc = get_media_library_stats_service()
                svc.invalidate_bucket_paths(
                    [src_folder.parent, target_dir], kinds=("image",)
                )
                run_async_from_ui(lambda: svc.refresh(min_interval_seconds=0))
            except Exception:
                logger.debug("移动图文文件夹后刷新媒体库统计失败", exc_info=True)
            return dst
        except Exception as e:
            user_log.warning(f"[文件整理] ⚠️ 文件夹移动失败（不影响发布结果）：{e}")
            logger.error("移动文件夹失败 src=%s dst=%s: %s", src_folder, target_dir, e, exc_info=True)
            return None

    @staticmethod
    def _do_move(
        src: Path,
        target_dir: Path,
        basename: str,
        user_log: logging.Logger,
    ) -> Optional[Path]:
        """将 src 移动到 target_dir，同名文件自动追加序号。返回实际目标路径，失败时返回 None。"""
        if not src.exists():
            user_log.warning(f"[文件整理] ⚠️ 源文件不存在，跳过移动：{src}")
            return None
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            dst = PostPublishFileHandler._unique_dst(target_dir, basename)
            shutil.move(str(src), str(dst))
            user_log.info(f"[文件整理] ✅ 已将 {basename} 移动至 {target_dir}/")
            return dst
        except Exception as e:
            user_log.warning(f"[文件整理] ⚠️ 文件操作失败（不影响发布结果）：{e}")
            logger.error("移动文件失败 src=%s dst=%s: %s", src, target_dir, e, exc_info=True)
            return None

    @staticmethod
    def _do_delete_folder(
        src_folder: Path,
        user_log: logging.Logger,
    ) -> bool:
        """删除整个图片文件夹（shutil.rmtree）。返回是否成功。"""
        if not src_folder.exists():
            user_log.warning(f"[文件整理] ⚠️ 源文件夹不存在，跳过删除：{src_folder}")
            return False
        try:
            shutil.rmtree(str(src_folder))
            user_log.info(f"[文件整理] ✅ 已删除文件夹 {src_folder.name}")
            # 刷新媒体库统计
            try:
                from src.services.material.media_library_stats_service import get_media_library_stats_service
                from src.ui.utils.async_helper import run_async_from_ui
                svc = get_media_library_stats_service()
                svc.invalidate_bucket_paths([src_folder.parent], kinds=("image",))
                run_async_from_ui(lambda: svc.refresh(min_interval_seconds=0))
            except Exception:
                logger.debug("删除图文文件夹后刷新媒体库统计失败", exc_info=True)
            return True
        except Exception as e:
            user_log.warning(f"[文件整理] ⚠️ 文件夹删除失败（不影响发布结果）：{e}")
            logger.error("删除文件夹失败 src=%s: %s", src_folder, e, exc_info=True)
            return False

    @staticmethod
    def _do_delete(
        src: Path,
        basename: str,
        user_log: logging.Logger,
    ) -> bool:
        """删除 src 文件。返回是否成功。"""
        if not src.exists():
            user_log.warning(f"[文件整理] ⚠️ 源文件不存在，跳过删除：{src}")
            return False
        try:
            os.remove(str(src))
            user_log.info(f"[文件整理] ✅ 已删除 {basename}")
            return True
        except Exception as e:
            user_log.warning(f"[文件整理] ⚠️ 文件操作失败（不影响发布结果）：{e}")
            logger.error("删除文件失败 src=%s: %s", src, e, exc_info=True)
            return False

    @staticmethod
    def _unique_dst(target_dir: Path, basename: str) -> Path:
        """若目标目录内已有同名文件，追加 _1、_2… 后缀。"""
        dst = target_dir / basename
        if not dst.exists():
            return dst
        stem = Path(basename).stem
        suffix = Path(basename).suffix
        i = 1
        while True:
            dst = target_dir / f"{stem}_{i}{suffix}"
            if not dst.exists():
                return dst
            i += 1

    @staticmethod
    def _normalize_file_path(fp: str) -> str:
        """标准化 file_path 用于分组 key 比较（取逗号分隔后排序拼接，小写）。"""
        prefix = PostPublishFileHandler._FOLDER_MARKER_PREFIX
        parts = sorted(
            p.strip().lower() for p in fp.split(",")
            if p.strip() and not p.strip().startswith(prefix)
        )
        return ",".join(parts)

    _FOLDER_MARKER_PREFIX = "__FOLDER__:"

    @staticmethod
    def _extract_folder_path(fp: str) -> str:
        """从 file_path 字符串中提取 __FOLDER__: 标记后的文件夹路径。

        若不含此标记（散图或视频任务），返回空字符串。
        """
        prefix = PostPublishFileHandler._FOLDER_MARKER_PREFIX
        for part in fp.split(","):
            part = part.strip()
            if part.startswith(prefix):
                return part[len(prefix):].strip()
        return ""

    @staticmethod
    def _split_file_paths(fp: str) -> List[str]:
        """将 file_path 字符串按逗号分割，返回去空格后的列表，自动过滤文件夹来源标记。"""
        prefix = PostPublishFileHandler._FOLDER_MARKER_PREFIX
        return [
            p.strip() for p in fp.split(",")
            if p.strip() and not p.strip().startswith(prefix)
        ]

    @staticmethod
    def _detect_file_type(fp: str) -> str:
        """根据文件扩展名判断 video / image。"""
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        paths = PostPublishFileHandler._split_file_paths(fp)
        if paths and Path(paths[0]).suffix.lower() in image_exts:
            return "image"
        return "video"
