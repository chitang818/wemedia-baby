"""
批量发布任务 — 领域术语、类型定义与契约
文件路径：src/ui/pages/publish/batch_task_definitions.py

本模块只放 **类型、枚举、常量与术语映射**，不含业务分支逻辑。
所有定义与产品规范文档保持一致：
  docs/01总文档/批量视频/批量视频/批量视频（批量图文）预览及发布任务生成逻辑.md

批量视频页 (batch_task_creation_page) 与批量图文页 (image_batch_task_creation_page)
共用本模块中的定义。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from typing_extensions import TypedDict


# =========================================================================
# 1. 预览任务 (Preview Task)
# =========================================================================
#
# 产品定义：
#   显示在批量任务界面表格中的行。数量仅与选中的「账号/账号组个数」×
#  「发布时间个数」有关，与账号组内子账号数量无关。
#
# 代码中的形态：
#   generate_batch_tasks_isolated(..., expanded_accounts=None) 的产出 dict。
#   账号组以 platform="account_group" 的单行占位（不展开为成员）。
#   若某些账号/组没有被分配算法覆盖，页面补全「待配置」占位行。

class PreviewTask(TypedDict, total=False):
    """预览表格一行的数据结构。

    字段与 ``_build_task`` 输出兼容；额外可选字段以下划线开头，
    供预览/排除逻辑内部使用。
    """
    # 核心字段 —— 与 publish_record 写库字段一致
    user_id: int
    platform: str
    platform_username: str
    platform_account_id: Optional[int]
    file_path: str
    file_type: str
    title: str
    description: str
    tags: str
    cover_path: Optional[str]
    poi_info: str
    wechat_empty_location_open_picker: Optional[bool]
    micro_app_info: str
    cart_info: str
    anchor_info: str
    privacy_settings: str
    scheduled_publish_time: Optional[str]


# =========================================================================
# 2. 发布任务 (Publish Task)
# =========================================================================
#
# 产品定义：
#   点击【添加到发布列表】后写入发布列表的任务。
#   若选中的是账号组，一条预览任务展开为「组内子账号数」条发布任务，
#   除账号外其余字段一致。
#
# 代码中的形态：
#   generate_batch_tasks_isolated(..., expanded_accounts=<展开后列表>) 的产出。
#   写库前还经过排除过滤、校验、去重守卫、原创声明剥离。

class PublishTaskPayload(TypedDict, total=False):
    """即将写入 ``publish_record`` 的任务 dict，与 ``_build_task`` 输出一致。"""
    user_id: int
    platform: str
    platform_username: str
    platform_account_id: Optional[int]
    file_path: str
    file_type: str
    title: str
    description: str
    tags: str
    cover_path: Optional[str]
    poi_info: str
    wechat_empty_location_open_picker: Optional[bool]
    micro_app_info: str
    cart_info: str
    anchor_info: str
    privacy_settings: str
    scheduled_publish_time: Optional[str]
    task_source: Optional[str]


# =========================================================================
# 3. 视频池 (Media Pool) 作用域
# =========================================================================
#
# 产品定义：
#   「自动匹配」时，每个账号/账号组各有独立的视频池（对应各自的媒体库目录）。
#   「手动设置」时，所有选中的账号/账号组共享同一视频池。
#   无论哪种模式：同一视频仅分配给一个预览任务，不可重复使用。

class MediaPoolScope(Enum):
    """视频池的隔离级别。"""
    PER_OWNER_AUTO = "per_owner_auto"
    """自动匹配：每个账号/每个账号组使用各自独立的视频池（媒体库目录），互不混用。

    对应 video_list 元素上的 _group_id / _assigned_account_id 标记，
    驱动 generate_batch_tasks_isolated 的隔离分支。
    """

    SHARED_MANUAL = "shared_manual"
    """手动设置：所有选中的账号/账号组共享同一视频池。

    video_list 元素无隔离标记，generate_batch_tasks_isolated
    退化为整体顺序块分配（或账号组全量复制分配）。
    """


# =========================================================================
# 4. 素材取用策略 (Media Pick Strategy)
# =========================================================================
#
# 产品文档（第 3、4 节）定义三种取视频规则：顺序 / 随机 / 循环。
#
# 项目中已有两个维度的「策略」，需要区分：
#   A) media_assign_strategy.AssignStrategy（ROUND_ROBIN / RANDOM / AVERAGE）
#      —— 作用于「将一批文件分配到多个目标账号」，即目标维度。
#      —— 使用场景：视频库页面分配文件、批量页从媒体库对话框导入。
#   B) BatchMediaPickStrategy（本枚举）
#      —— 作用于「从单个账号/组的视频池中取第 N 个视频」，即池内取用维度。
#      —— 使用场景：自动匹配 (MaterialAutoMatcher.fetch_materials)、
#         手动场景下的共享池按顺序/随机/循环分配到预览任务。
#
# 两者正交，可独立配置。

class BatchMediaPickStrategy(Enum):
    """从视频池（单个目标的媒体文件列表）中取视频的策略。"""
    SEQUENTIAL = "sequential"
    """顺序：按文件名自然排序依次取，不跳过不重复（现有默认行为）。"""

    RANDOM = "random"
    """随机：对候选列表随机打乱后依次取（每次重新 shuffle）。"""

    CYCLIC = "cyclic"
    """循环：文件取完后回到开头继续取（当时间槽多于视频数时）。

    语义说明：循环作用于「池内文件列表」维度；若视频 3 个、时间 5 个，
    则分配结果为 v1 v2 v3 v1 v2。与 generate_batch_tasks 中 time_slots
    的 % 取模语义一致。
    """

    @classmethod
    def from_str(cls, value: str) -> "BatchMediaPickStrategy":
        for member in cls:
            if member.value == value:
                return member
        return cls.SEQUENTIAL

    def display_name(self) -> str:
        return {
            BatchMediaPickStrategy.SEQUENTIAL: "顺序",
            BatchMediaPickStrategy.RANDOM: "随机",
            BatchMediaPickStrategy.CYCLIC: "循环",
        }[self]


PICK_STRATEGY_DISPLAY_NAMES: List[str] = [
    s.display_name() for s in BatchMediaPickStrategy
]


def pick_strategy_from_display_name(name: str) -> BatchMediaPickStrategy:
    for s in BatchMediaPickStrategy:
        if s.display_name() == name:
            return s
    return BatchMediaPickStrategy.SEQUENTIAL


# =========================================================================
# 5. video_list 排列契约
# =========================================================================
#
# video_list: List[dict] 中元素的 append 顺序 == 分配顺序。
# generate_batch_tasks 按索引消耗，不做内部排序。
#
# 当前列表维护方式：
#   - 文件选择：sorted(filenames) + 逐个 append
#   - 自动匹配：auto_match_for_accounts → new_items 按 matcher 文件名排序
#   - 手动从视频库：按对话框勾选顺序
#   - 无拖拽/重排 UI（预览表只读）
#
# 元素上的内部标记（均以下划线开头）：
#   _group_id:              所属账号组 ID（自动匹配时写入）
#   _assigned_account_id:   所属独立账号 ID（自动匹配时写入）
#   _auto_matched:          True 表示由自动匹配添加（清空视频时可区分手动/自动）
#
# 这些标记驱动 generate_batch_tasks_isolated 的隔离分支。
# 若后续增加拖拽排序或视频去重，需同步更新此契约。


# =========================================================================
# 5a. 手动流程 A / B（待产品确认）
# =========================================================================
#
# 文档中定义两种手动流程：
#   流程 A（先时间后视频）：预览行数 = 账号/组数 × 时间数
#   流程 B（先视频后时间）：预览行数 = 共享池视频数
#
# 当前实现等价于流程 B 的变体：预览行数由 generate_batch_tasks_isolated
# 根据账号与视频的 min 决定，时间维度做 % 取模循环。
#
# 若需要支持流程 A，需增加 ManualWorkflowPhase 枚举并在
# build_preview_tasks 中按 phase 切换预览行数公式。
# 此功能标记为「V2 — 按产品确认后实施」，当前版本不包含。


# =========================================================================
# 6. 文案回写时序契约
# =========================================================================
#
# build_preview_tasks / build_publish_tasks 只消费 common_fields 与
# video_list 中已写好的 title/description/tags。
#
# 文案的「回写到 video_list」由页面在调用 builder 之前完成
# （_reapply_description_to_all_videos），builder 不负责拉文案库。
#
# common_fields 中的 title / description / tags_str 仅在
# apply_description_to_all_tasks=True 时有值，否则为空字符串。
# _build_task 内 per-video 字段优先级高于 common。


# =========================================================================
# 7. 辅助：batch_task_fingerprint 类型别名
# =========================================================================

# =========================================================================
# 7a. 账号 / 账号组互斥规则
# =========================================================================
#
# 当前产品约束：
#   选择发布对象弹窗 (publish_target_selection_dialog) 每次返回的结果
#   要么全部是独立账号 (type="account")，要么全部是账号组 (type="group")，
#   不会混合。_apply_selection_result 每次用返回值替换 selected_accounts，
#   因此 selected_accounts 天然互斥。
#
# 防御策略：
#   如果将来弹窗允许混选，build_publish_tasks_for_batch 中应在展开前
#   检查并拒绝混选（InfoBar 提示 + 早期返回）。


BatchTaskFingerprint = Tuple[str, str, str, str]
"""(platform, platform_username, file_path, scheduled_publish_time)"""


# =========================================================================
# 8. 策略映射：AssignStrategy ↔ BatchMediaPickStrategy
# =========================================================================
#
# 两者正交、不可互相替代。映射仅在 UI 需要统一显示或配置时使用。
#
# AssignStrategy（目标维度）:
#   ROUND_ROBIN → 轮流分配: 第1个文件给目标A, 第2个给B, 第3个给A...
#   RANDOM      → 随机分配: 打乱后依次分配
#   AVERAGE     → 平均分配: 每个目标尽量等量
#
# BatchMediaPickStrategy（池内取用维度）:
#   SEQUENTIAL  → 顺序: 按文件名排序
#   RANDOM      → 随机: shuffle 后取
#   CYCLIC      → 循环: 取到末尾回到开头继续
