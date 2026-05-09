# -*- coding: utf-8 -*-
"""
Fluent 右键菜单共用工具
文件路径：src/ui/components/fluent_context_menu.py
功能：RoundMenu 顶层父级、C++ 对象失效探测、应用失焦或主窗口最小化/隐藏时关闭弹层，供各页复用。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QWidget


class _CloseRoundMenuOnHostWindowChange(QObject):
    """主窗口最小化、隐藏时关闭仍挂起的 RoundMenu（Windows 上仅靠 applicationStateChanged 往往不够）。"""

    def __init__(self, menu: QWidget) -> None:
        super().__init__(menu)
        self._menu = menu

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        et = event.type()
        if et == QEvent.Type.WindowStateChange:
            w = watched if isinstance(watched, QWidget) else None
            if w is not None and w.isWindow():
                try:
                    if w.windowState() & Qt.WindowState.WindowMinimized and self._menu.isVisible():
                        self._menu.close()
                except RuntimeError:
                    pass
        elif et == QEvent.Type.Hide:
            w = watched if isinstance(watched, QWidget) else None
            if w is not None and w.isWindow():
                try:
                    if self._menu.isVisible():
                        self._menu.close()
                except RuntimeError:
                    pass
        return False


def round_menu_parent(widget: Optional[QWidget]) -> Optional[QWidget]:
    """RoundMenu 的 parent 优先用业务控件所在顶层窗口，避免挂在内嵌控件上主题/阴影异常。"""
    if widget is None:
        return None
    return widget.window()


def is_round_menu_alive(menu) -> bool:
    """主窗口重建等导致底层 QMenu 已销毁时返回 False，需重新 _init。"""
    if menu is None:
        return False
    try:
        menu.actions()
        return True
    except RuntimeError:
        return False


def install_round_menu_close_on_app_inactive(menu: Optional[QWidget]) -> None:
    """在应用失焦、主窗口最小化/隐藏时关闭仍可见的 RoundMenu。

    qfluentwidgets 的 ``RoundMenu.exec`` 仅 ``show`` 弹层（非阻塞 ``QMenu.exec``）；
    用户未点选即 Alt-Tab / 任务栏切到其他程序时，``Qt.Popup`` 在 Windows 上可能仍留在最前。
    另：最小化主程序时，部分环境下 ``ApplicationState`` 仍为 Active，故需监听父顶层窗口状态。
    每个 ``RoundMenu`` 实例创建后调用一次即可；菜单销毁时会自动断开信号与事件过滤器。
    """
    if menu is None:
        return
    if getattr(menu, "_wb_round_menu_inactive_close_installed", False):
        return
    app = QApplication.instance()
    if app is None:
        return
    menu._wb_round_menu_inactive_close_installed = True  # type: ignore[attr-defined]

    def _on_state(state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            return
        try:
            if menu.isVisible():
                menu.close()
        except RuntimeError:
            pass

    app.applicationStateChanged.connect(_on_state)

    host_filter: Optional[_CloseRoundMenuOnHostWindowChange] = None
    host: Optional[QWidget] = menu.parentWidget()
    while host is not None and not host.isWindow():
        host = host.parentWidget()
    if host is None:
        host = menu.window()
    # 避免对菜单自身装过滤器；无可靠顶层窗口时仅依赖 applicationStateChanged
    if host is not None and host is not menu:
        host_filter = _CloseRoundMenuOnHostWindowChange(menu)
        host.installEventFilter(host_filter)
        menu._wb_round_menu_host_filter = host_filter  # type: ignore[attr-defined]  # 防止被 GC

    def _teardown(*_args: object) -> None:
        try:
            app.applicationStateChanged.disconnect(_on_state)
        except TypeError:
            pass
        if host is not None and host_filter is not None:
            try:
                host.removeEventFilter(host_filter)
            except RuntimeError:
                pass

    menu.destroyed.connect(_teardown)
