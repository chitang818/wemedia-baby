"""
批量发布：发布对象选择弹窗（账号/账号组）
文件路径：src/pro_features/batch/dialogs/publish_target_selection_dialog.py

说明：
- 作为批量视频/批量图文等页面的可复用模块
- 基于现有 AccountSelectionDialog，统一启用多选账号 + 多选账号组
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QWidget


async def select_publish_targets(
    parent: QWidget,
    accounts: List[Dict[str, Any]],
    groups: Optional[List[Dict[str, Any]]] = None,
    initial_account_ids: Optional[List[str]] = None,
    initial_group_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """弹出选择发布对象弹窗，返回 AccountSelectionDialog 的选择结果。

    Returns:
        - None：用户取消
        - {'type': 'account', 'data': account | [account, ...]}
        - {'type': 'group', 'data': group | [group, ...]}
    """
    from src.ui.dialogs.account_selection_dialog import AccountSelectionDialog

    dialog = AccountSelectionDialog(parent.window() if parent else None)
    dialog.set_data(
        accounts,
        groups or [],
        show_group_nav=True,
        multi_select=True,
        ctrl_multi_select=True,
        initial_account_ids=initial_account_ids,
        initial_group_ids=initial_group_ids,
    )
    dialog.setWindowModality(Qt.WindowModality.WindowModal)

    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()

    def on_finished(code: int):
        if future.done():
            return
        try:
            r = dialog.get_selected_result() if code == int(QDialog.DialogCode.Accepted) else None
        except Exception as exc:
            future.set_exception(exc)
        else:
            future.set_result(r)

    dialog.finished.connect(on_finished)
    dialog.show()
    return await future

