"""
安全展示 Fluent InfoBar：推迟到下一事件循环、使用顶层 window 作 parent、失败时降级为对话框。

避免在大量同步 UI 更新后立即创建 InfoBar，与 qfluentwidgets 的 CustomStyleSheet/eventFilter 重入
叠加时出现 ``Internal C++ object (InfoBar) already deleted``。
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

try:
    import shiboken6 as _shiboken6
except ImportError:
    _shiboken6 = None  # type: ignore[misc, assignment]


def _qobject_alive(obj: Optional[QWidget]) -> bool:
    if obj is None:
        return False
    if _shiboken6 is None:
        return True
    try:
        return bool(_shiboken6.isValid(obj))
    except Exception:
        return True


def _toast_parent(widget: Optional[QWidget]) -> Optional[QWidget]:
    if widget is None:
        return None
    try:
        w = widget.window()
        if w is not None:
            return w
    except Exception:
        pass
    return widget


def show_success_toast(
    parent_widget: Optional[QWidget],
    title: str,
    content: str,
    *,
    duration: int = 3000,
) -> None:
    """下一帧在主窗口上显示成功 InfoBar；失败则 ``show_info`` 降级。"""

    parent = _toast_parent(parent_widget)

    def _show() -> None:
        if not _qobject_alive(parent):
            logger.debug("safe_info_bar: 父窗口无效，跳过成功提示: %s", title)
            return
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition

            InfoBar.success(
                title=title,
                content=content,
                parent=parent,
                position=InfoBarPosition.TOP,
                duration=duration,
            )
        except RuntimeError as e:
            logger.warning("InfoBar.success 失败，降级为对话框: %s", e)
            try:
                from src.ui.utils.fluent_dialogs import show_info

                show_info(parent_widget if _qobject_alive(parent_widget) else parent, title, content)
            except Exception:
                logger.exception("safe_info_bar: 降级 show_info 失败")
        except Exception:
            logger.exception("safe_info_bar: 成功提示异常")
            try:
                from src.ui.utils.fluent_dialogs import show_info

                show_info(parent_widget if _qobject_alive(parent_widget) else parent, title, content)
            except Exception:
                pass

    QTimer.singleShot(0, _show)


def show_error_toast(
    parent_widget: Optional[QWidget],
    title: str,
    content: str,
    *,
    duration: int = 5000,
) -> None:
    """下一帧在主窗口上显示错误 InfoBar；失败则 ``show_error`` 降级。"""

    parent = _toast_parent(parent_widget)

    def _show() -> None:
        if not _qobject_alive(parent):
            logger.debug("safe_info_bar: 父窗口无效，跳过错误提示: %s", title)
            return
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition

            InfoBar.error(
                title=title,
                content=content,
                parent=parent,
                position=InfoBarPosition.TOP,
                duration=duration,
            )
        except RuntimeError as e:
            logger.warning("InfoBar.error 失败，降级为对话框: %s", e)
            try:
                from src.ui.utils.fluent_dialogs import show_error

                show_error(parent_widget if _qobject_alive(parent_widget) else parent, title, content)
            except Exception:
                logger.exception("safe_info_bar: 降级 show_error 失败")
        except Exception:
            logger.exception("safe_info_bar: 错误提示异常")
            try:
                from src.ui.utils.fluent_dialogs import show_error

                show_error(parent_widget if _qobject_alive(parent_widget) else parent, title, content)
            except Exception:
                pass

    QTimer.singleShot(0, _show)
