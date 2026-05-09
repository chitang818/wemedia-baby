"""
FFmpeg 缺失时的弹窗及下载逻辑
文件路径：src/ui/utils/ffmpeg_dialog.py
功能：当软件操作中需要 FFmpeg 但未找到时，弹窗提示用户是否下载
"""

from typing import Optional
import logging

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import QTimer, QPoint

logger = logging.getLogger(__name__)

# 右上角边距
STATE_TOOLTIP_MARGIN = 24


def _move_state_tooltip_to_bottom_right(tooltip: QWidget) -> None:
    """将 StateToolTip 移动到父窗口右上角"""
    p = tooltip.parent()
    if p and p.isVisible():
        # 右上角：x 在右侧留边距，y 固定为上边距
        x = p.width() - tooltip.width() - STATE_TOOLTIP_MARGIN
        y = STATE_TOOLTIP_MARGIN
        tooltip.move(max(0, x), max(0, y))


def is_ffmpeg_available_for_preview() -> bool:
    """检查 FFmpeg 是否可用于视频/图片预览"""
    from src.utils.video_metadata import check_ffmpeg_available

    return bool(check_ffmpeg_available())


def show_ffmpeg_missing_dialog(parent: Optional[QWidget] = None) -> bool:
    """当 FFmpeg 未找到时，弹窗提示用户是否下载。

    弹窗文案：视频及图片预览功能不可用，是否需要下载ffmpeg插件
    - 确定：执行设置中的下载 FFmpeg 功能
    - 取消：关闭弹窗

    Returns:
        True 表示用户点击了确定（已启动下载流程），False 表示用户点击了取消
    """
    from src.ui.utils.fluent_dialogs import show_confirm

    confirmed = show_confirm(
        parent or QApplication.activeWindow(),
        "FFmpeg 未安装",
        "视频及图片预览功能不可用，是否需要下载ffmpeg插件？"
    )
    if not confirmed:
        return False

    _run_ffmpeg_download(parent or QApplication.activeWindow())
    return True


def _run_ffmpeg_download(parent: Optional[QWidget]) -> None:
    """执行 FFmpeg 下载（与设置页相同逻辑）"""
    from src.ui.utils.async_helper import run_async_from_ui
    from src.utils.ffmpeg_installer import FFMPEG_MANUAL_DOWNLOAD_URL

    win = (parent.window() if parent else None) or QApplication.activeWindow()

    tooltip = None
    try:
        from qfluentwidgets import StateToolTip
        if win:
            tooltip = StateToolTip("正在下载 FFmpeg", "0%", win)
            tooltip.show()
            # 延迟移动到右下角，确保控件已完成布局
            QTimer.singleShot(50, lambda: _move_state_tooltip_to_bottom_right(tooltip))
    except ImportError:
        pass

    def progress_cb(current: int, total: int):
        if tooltip and total and total > 0:
            pct = min(100, int(100 * current / total))
            tooltip.setContent(f"{pct}%")
        elif tooltip:
            tooltip.setContent("正在下载...")

    async def download_ffmpeg_task():
        try:
            from src.utils.ffmpeg_installer import download_and_install_ffmpeg_async

            ok, msg = await download_and_install_ffmpeg_async(progress_callback=progress_cb)

            if tooltip:
                tooltip.setContent(msg[:60] + "…" if len(msg) > 60 else msg)
                tooltip.setState(True)

            if ok:
                from src.utils import video_metadata
                video_metadata._initialize_ffmpeg_path(force_refresh=True)
                from src.ui.utils.fluent_dialogs import show_info
                show_info(parent, "FFmpeg 已安装", msg)
            else:
                from src.ui.utils.fluent_dialogs import show_error
                show_error(
                    parent,
                    "下载失败",
                    msg + "\n\n可手动从 " + FFMPEG_MANUAL_DOWNLOAD_URL + " 下载。"
                )
        except Exception as e:
            logger.exception("下载 FFmpeg 异常")
            if tooltip:
                tooltip.setContent(str(e)[:50] + "…")
                tooltip.setState(True)
            from src.ui.utils.fluent_dialogs import show_error
            show_error(parent, "下载失败", str(e))

    try:
        run_async_from_ui(download_ffmpeg_task)
    except Exception as e:
        logger.error(f"启动 FFmpeg 下载任务失败: {e}")
        if tooltip:
            tooltip.setContent("启动失败，请重试")
            tooltip.setState(True)
        from src.ui.utils.fluent_dialogs import show_error
        show_error(parent, "启动失败", "无法启动下载任务，请稍后重试")
