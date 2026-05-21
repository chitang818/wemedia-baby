# -*- coding: utf-8 -*-
"""
视频号发布步骤链

步骤对照表（10步，视频发布顺序）：
    step_01_home.py         → NavigateHomeStep       → 进入创作者服务中心
    step_02_entry.py        → EnterPublishEntryStep  → 查找发布入口并进入
    step_03_upload.py       → UploadMediaStep        → 上传视频/图片
    step_04_cover.py        → CoverSettingStep       → 封面设置
    step_05A_image_title.py → ImageTitleStep         → 填写图文标题
    step_05B_description.py → MetadataFillStep       → 填写描述
    step_08A_image_music.py → ImageTextMusicStep     → 选择并设置背景音乐（占位）
    step_06_location.py     → LocationSettingStep    → 位置设置
    step_07_link.py         → LinkSettingStep        → 链接设置
    step_08B_schedule.py    → ScheduleSettingStep    → 定时发表设置
    step_08C_short_title.py → ShortTitleStep         → 短标题
    step_08D_original.py    → OriginalDeclareStep    → 声明原创
    step_09_submit.py       → SubmitStep             → 点击发布

注意：视频与图文共用以上步骤，图文发布顺序后续补充。
"""

from .step_01_home import NavigateHomeStep
from .step_02_entry import EnterPublishEntryStep
from .step_03_upload import UploadMediaStep
from .step_04_cover import CoverSettingStep
from .step_05A_image_title import ImageTitleStep
from .step_05B_description import MetadataFillStep
from .step_08A_image_music import ImageTextMusicStep
from .step_06_location import LocationSettingStep
from .step_07_link import LinkSettingStep
from .step_08B_schedule import ScheduleSettingStep
from .step_08C_short_title import ShortTitleStep
from .step_08D_original import OriginalDeclareStep
from .step_09_submit import SubmitStep

__all__ = [
    "NavigateHomeStep",
    "EnterPublishEntryStep",
    "UploadMediaStep",
    "CoverSettingStep",
    "ImageTitleStep",
    "MetadataFillStep",
    "ImageTextMusicStep",
    "LocationSettingStep",
    "LinkSettingStep",
    "ScheduleSettingStep",
    "ShortTitleStep",
    "OriginalDeclareStep",
    "SubmitStep",
]
