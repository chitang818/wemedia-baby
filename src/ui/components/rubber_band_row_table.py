# -*- coding: utf-8 -*-
"""
Excel 式行框选表格（Fluent TableWidget 子类）

用于卡片内「整行多选 + 橡皮筋框选」场景；需在 viewport 上优先处理 MouseMove 时配合
_ViewportRowSelectFilter 使用（见本文件底部）。

其他页面复用时：继承本类或直接使用 RubberBandRowSelectTable，并设置
SelectRows + ExtendedSelection，勿对整表 setToolTip（Fluent 深色下易出现黑条）。

崩溃防护（两处关键决策）：
1. QRubberBand parent 必须是 self（table）而非 viewport()。
   若设为 viewport()，Fluent StyleSheetManager 遍历 viewport.children() 时遇到
   QRubberBand 会触发 C 层 access violation。parent=self 后 viewport() 不再包含
   QRubberBand，坐标转换通过 _vp_offset() 补偿。

2. 禁止在懒加载页面的 showEvent 调用栈或 Fluent stacked_widget 动画期间调用
   setBorderVisible / setBorderRadius / setCustomStyleSheet / setCustomStyleSheet 等
   Fluent 样式 API。这些方法内部调用 setProperty(LIGHT/DARK_QSS_KEY) 触发
   CustomStyleSheetWatcher → addStyleSheet → widget.setStyleSheet，在动画期间执行
   会导致 C 层 access violation。
   解决方案：
   a. BasePage.showEvent 中懒加载改为 QTimer.singleShot(0, self._ensure_content)，
      确保 _setup_content 在 showEvent 返回后才执行。
   b. __init__ 阶段（_setup_content 被 QTimer 调度到的帧内）直接 setStyleSheet 附加
      2px padding，完全绕过 Fluent 样式管理器，不触发 watcher 链。
"""
from __future__ import annotations

from typing import List, Optional, Set

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QItemSelection, QItemSelectionModel
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QAbstractItemView, QRubberBand

from qfluentwidgets import TableWidget, isDarkTheme


class RubberBandRowSelectTable(TableWidget):
    """左键拖出矩形框选行（与 Excel 类似：与框相交的行被选中）。

    - 无修饰键：框选结果替换当前选区。
    - Ctrl：越过拖动阈值时快照当前选区，再与框内行取并集。
    - Shift：不启用本类自定义框选，交给 ExtendedSelection 默认行为（如 Shift+点选扩展）。

    越过阈值后对 viewport 调用 grabMouse，避免鼠标移出表格区域后框选中断。
    """

    _RUBBER_THRESHOLD_PX = 4

    def __init__(self, parent=None):
        self._rubber: Optional[QRubberBand] = None
        super().__init__(parent)
        self._rb_origin: Optional[QPoint] = None
        self._rb_dragging: bool = False
        self._rb_additive: bool = False
        self._rb_preserve_rows: Set[int] = set()
        self._rb_shift_skip: bool = False
        self._last_rubber_key: Optional[tuple] = None
        self._rubber_commit_rows: Optional[Set[int]] = None
        self._pending_rubber_rows: Optional[List[int]] = None
        self._vp_grabbing: bool = False

        self.setDragEnabled(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.viewport().setMouseTracking(True)

        # parent=self 而非 viewport()，防止 Fluent addStyleSheet 遍历 viewport children 崩溃
        self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._rubber.hide()
        self._apply_rubber_band_style()

        self._vp_filter = _ViewportRowSelectFilter(self)
        self.viewport().installEventFilter(self._vp_filter)

        # 在 __init__ 阶段（非 showEvent 期间）附加 2px padding，安全且统一。
        # 不使用 setCustomStyleSheet/setBorderRadius 等 Fluent API，避免在懒加载
        # showEvent / Fluent 动画期间触发 StyleSheetManager watcher 递归导致 C 层崩溃。
        _default_padding_qss = "QTableView::item { padding-left: 2px; padding-right: 2px; }"
        self.setStyleSheet(self.styleSheet() + "\n" + _default_padding_qss)

    def _vp_offset(self) -> QPoint:
        """viewport 左上角相对于 table 自身的偏移（用于坐标转换）。"""
        vp = self.viewport()
        if vp is None:
            return QPoint(0, 0)
        return vp.mapToParent(QPoint(0, 0))

    def _apply_rubber_band_style(self) -> None:
        if self._rubber is None:
            return
        if isDarkTheme():
            self._rubber.setStyleSheet(
                "QRubberBand { border: 1px solid #63B3ED; background-color: rgba(99, 179, 237, 0.18); }"
            )
        else:
            self._rubber.setStyleSheet(
                "QRubberBand { border: 1px solid #217346; background-color: rgba(33, 115, 70, 0.15); }"
            )

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        et = event.type()
        if et in (
            QEvent.Type.PaletteChange,
            QEvent.Type.StyleChange,
            QEvent.Type.ThemeChange,
        ):
            self._apply_rubber_band_style()

    def _release_viewport_grab(self) -> None:
        vp = self.viewport()
        if vp is not None and self._vp_grabbing:
            vp.releaseMouse()
            self._vp_grabbing = False

    def _selected_row_indices(self) -> Set[int]:
        sm = self.selectionModel()
        if sm is None:
            return set()
        return {idx.row() for idx in sm.selectedIndexes()}

    def _rows_intersecting_vp_rect(self, rect: QRect) -> List[int]:
        """viewport 坐标系下，与矩形相交的数据行行号（整行宽度参与判断）。

        使用 rowAt() 二分定位首行/末行，O(log n) 替代原来的全行遍历 O(n)。
        5000 行时框选拖动每帧约减少 4990 次无效 rowViewportPosition 调用。
        """
        vp = self.viewport()
        if vp is None:
            return []
        m = self.model()
        if m is None:
            return []
        row_count = m.rowCount()
        if row_count == 0:
            return []
        w = vp.width()
        rect_top = rect.top()
        rect_bottom = rect.bottom()

        # 用 rowAt 定位矩形顶边命中的行（首行）；若在所有行上方则从第0行开始
        first = self.rowAt(max(rect_top, 0))
        if first < 0:
            first = 0

        out: List[int] = []
        for r in range(first, row_count):
            y = self.rowViewportPosition(r)
            if y > rect_bottom:
                break
            h = max(self.rowHeight(r), 1)
            if y + h >= rect_top:
                out.append(r)
        return out

    def _handle_drag_press(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._rubber is not None:
            self._rubber.hide()
        self._last_rubber_key = None
        self._rubber_commit_rows = None
        self._rb_dragging = False
        self._rb_preserve_rows = set()
        self._release_viewport_grab()
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._rb_shift_skip = True
            self._rb_origin = None
            return
        self._rb_shift_skip = False
        self._rb_origin = event.position().toPoint()
        self._rb_additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

    def _handle_drag_move(self, event: QMouseEvent) -> bool:
        if self._rb_shift_skip or self._rb_origin is None:
            return False
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            return False
        cur = event.position().toPoint()
        vp_rect = QRect(self._rb_origin, cur).normalized()
        if (
            vp_rect.width() < self._RUBBER_THRESHOLD_PX
            and vp_rect.height() < self._RUBBER_THRESHOLD_PX
        ):
            return False

        first_frame = not self._rb_dragging
        if first_frame:
            self._rb_dragging = True
            if self._rb_additive:
                self._rb_preserve_rows = set(self._selected_row_indices())
            vp = self.viewport()
            if vp is not None and not self._vp_grabbing:
                vp.grabMouse()
                self._vp_grabbing = True

        rb = self._rubber
        if rb is None:
            return True
        # viewport 坐标 → table 坐标（QRubberBand parent 是 self）
        offset = self._vp_offset()
        rb.setGeometry(vp_rect.translated(offset))
        rb.show()
        rows = self._rows_intersecting_vp_rect(vp_rect)
        self._apply_rubber_selection(rows)
        return True

    def _handle_drag_release(self, event: QMouseEvent) -> None:
        """由 viewport 过滤器调用：清理橡皮筋状态并保存行集合。

        此时 mouseReleaseEvent 尚未被 QAbstractScrollArea 触发，
        把行集合存入 _pending_rubber_rows，等 mouseReleaseEvent 里同步重新提交。
        """
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_rubber_drag = self._rb_dragging
        commit = self._rubber_commit_rows

        if self._rubber is not None:
            self._rubber.hide()
        self._rb_origin = None
        self._rb_dragging = False
        self._rb_additive = False
        self._rb_preserve_rows = set()
        self._rb_shift_skip = False
        self._last_rubber_key = None
        self._rubber_commit_rows = None
        self._release_viewport_grab()

        if was_rubber_drag and commit is not None:
            self._pending_rubber_rows = sorted(commit)

        self._force_repaint()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """重写：让 super() 完成 Qt 内部清理，再立即同步恢复橡皮筋选区。

        事件顺序：
          viewport filter (_handle_drag_release) → sets _pending_rubber_rows
          → QAbstractScrollArea 触发本方法
          → super().mouseReleaseEvent() 可能用 ExtendedSelection ClearAndSelect 清掉多行选区
          → 我们立即重新提交选区
        """
        pending = self._pending_rubber_rows
        self._pending_rubber_rows = None
        super().mouseReleaseEvent(event)
        if pending is not None and event.button() == Qt.MouseButton.LeftButton:
            self._last_rubber_key = None
            self._apply_rubber_selection(pending)

    def _force_repaint(self) -> None:
        vp = self.viewport()
        if vp is not None:
            vp.repaint()
        vh = self.verticalHeader()
        if vh is not None:
            vh.repaint()

    @staticmethod
    def _contiguous_ranges(sorted_rows: List[int]) -> List[tuple]:
        if not sorted_rows:
            return []
        ranges: List[tuple] = []
        start = prev = sorted_rows[0]
        for r in sorted_rows[1:]:
            if r == prev + 1:
                prev = r
            else:
                ranges.append((start, prev))
                start = prev = r
        ranges.append((start, prev))
        return ranges

    def _apply_rubber_selection(self, rows_in_rect: List[int]) -> None:
        sm = self.selectionModel()
        m = self.model()
        if sm is None or m is None:
            return
        if self._rb_additive:
            target: Set[int] = self._rb_preserve_rows | set(rows_in_rect)
        else:
            target = set(rows_in_rect)
        key = tuple(sorted(target))
        if key == self._last_rubber_key:
            return
        self._last_rubber_key = key
        self._rubber_commit_rows = set(target)
        if not target:
            sm.clearSelection()
            self._force_repaint()
            return

        sorted_rows = sorted(target)
        ranges = self._contiguous_ranges(sorted_rows)
        sm.clearSelection()
        first = True
        for lo, hi in ranges:
            if lo < 0 or hi >= m.rowCount():
                continue
            top_left = m.index(lo, 0)
            bottom_right = m.index(hi, m.columnCount() - 1)
            sel = QItemSelection(top_left, bottom_right)
            if first:
                sm.select(
                    sel,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
                first = False
            else:
                sm.select(
                    sel,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
        self._force_repaint()


class _ViewportRowSelectFilter(QObject):
    """安装在 TableWidget.viewport 上，先于 Fluent 内部过滤器处理 MouseMove。"""

    def __init__(self, table: RubberBandRowSelectTable):
        super().__init__(table)
        self._table = table

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        et = event.type()
        if et == QEvent.Type.MouseButtonPress:
            self._table._handle_drag_press(event)
            return False
        if et == QEvent.Type.MouseMove:
            return self._table._handle_drag_move(event)
        if et == QEvent.Type.MouseButtonRelease:
            self._table._handle_drag_release(event)
            return False
        return False
