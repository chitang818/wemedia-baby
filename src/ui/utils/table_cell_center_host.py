"""
QTableWidget / Fluent TableWidget 单元格内子控件居中宿主。

从 publish_records_page 拆出，供发布时间弹窗等仍使用 setCellWidget 的表格复用。
"""

from typing import Dict, List, Optional

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QSize, QEvent, QObject, QPoint


class _TableViewportResizeDispatcher(QObject):
    """表格 viewport 级别单一 Resize 事件分发器。

    替代原先「每个 _TableCellCenterHost 各装一个 viewport eventFilter」的方案。
    5000 行时原方案会在 viewport 上累积 5000 个过滤器，每次鼠标/Resize 事件都走
    5000 次 eventFilter 链，严重拖慢 UI。
    此分发器只安装一次，viewport Resize 时批量通知所有已注册的 _TableCellCenterHost。
    """

    def __init__(self, viewport: QWidget):
        super().__init__(viewport)
        self._viewport = viewport
        self._hosts: List["_TableCellCenterHost"] = []
        viewport.installEventFilter(self)

    def register(self, host: "_TableCellCenterHost") -> None:
        self._hosts.append(host)

    def unregister(self, host: "_TableCellCenterHost") -> None:
        try:
            self._hosts.remove(host)
        except ValueError:
            pass

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._viewport and event.type() == QEvent.Type.Resize:
            for host in self._hosts:
                try:
                    host._on_viewport_resize()
                except RuntimeError:
                    pass
        return False


class _TableCellCenterHost(QWidget):
    """将单个子控件按父控件几何矩形摆放（默认水平居中）。

    Fluent TableWidget 末列由 TableItemDelegate 绘制圆角背景时与 QTableWidget
    的 indexWidget 布局存在偏置，嵌套 QLayout + stretch 在部分环境下仍会水平靠右；
    用 resize/show 时根据父尺寸直接 move 子控件，不依赖布局分配剩余空间。

    非最大化/拖拽改窗体大小时，QTableWidget 往往在首帧或视口 resize 之后才落定单元格
    几何；仅处理本控件 resizeEvent 会偶发错过最终尺寸。此处：立即居中 + 0ms 防抖再居中
    一次，并监听表格 viewport 的 Resize 再触发（与行内子控件 resize 互补）。

    竖直方向：indexWidget 偶发高于「行高」，仍用整高做 (h-h_btn)/2 会把按钮算得过低；
    用 min(自身高度, 当前行 rowHeight) 作为有效高度，并减去与 TableItemDelegate.margin(2)
    一致的上边距，使与相邻列文字区视觉中线对齐。

    水平方向：在「中间列 Stretch + 末列 Fixed」的窄表（如发布时间排期弹窗）中，末列
    indexWidget 偶发获得接近整行宽度的几何，此时若仍对子控件水平居中，按钮会落在行中
    央并压在「时间」列文字上。末列操作按钮应传 horizontal=\"right\"，将子控件贴齐宿主右缘。

    viewport 事件监听由 _TableViewportResizeDispatcher 统一管理，不再每行自行
    installEventFilter，避免大数据量下 5000 个过滤器堆积在同一 viewport 上。
    """

    # 与 qfluentwidgets.components.widgets.table_view.TableItemDelegate.margin 一致
    _FLUENT_CELL_V_MARGIN = 2

    # 表格 -> 分发器 弱引用字典，确保同一个 viewport 只装一次过滤器
    _dispatcher_map: Dict = {}

    def __init__(
        self,
        inner: QWidget,
        table,
        row: int,
        col: int,
        *,
        horizontal: str = "center",
        horizontal_margin: int = 4,
    ):
        super().__init__(table)
        self._table = table
        self._row = row
        self._col = col
        self._horizontal = horizontal if horizontal in ("center", "right") else "center"
        self._horizontal_margin = max(0, int(horizontal_margin))
        self._inner = inner
        self._dispatcher: Optional["_TableViewportResizeDispatcher"] = None
        inner.setParent(self)
        inner.show()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.timeout.connect(self._relayout_inner)
        vp = table.viewport() if callable(getattr(table, "viewport", None)) else None
        if vp is not None:
            # 获取或创建共享分发器（每个 viewport 实例只创建一次）
            dispatcher = _TableCellCenterHost._dispatcher_map.get(id(vp))
            if dispatcher is None or not self._is_dispatcher_alive(dispatcher):
                dispatcher = _TableViewportResizeDispatcher(vp)
                _TableCellCenterHost._dispatcher_map[id(vp)] = dispatcher
            dispatcher.register(self)
            self._dispatcher = dispatcher

    @staticmethod
    def _is_dispatcher_alive(obj) -> bool:
        try:
            obj.parent()
            return True
        except RuntimeError:
            return False

    def __del__(self):
        if self._dispatcher is not None:
            try:
                self._dispatcher.unregister(self)
            except Exception:
                pass

    def _on_viewport_resize(self) -> None:
        """由 _TableViewportResizeDispatcher 在 viewport Resize 时调用。"""
        self._schedule_relayout()

    def _effective_row_height(self) -> int:
        tw = self._table
        if tw is None:
            return 0
        vp = tw.viewport()
        if vp is None or not self.isVisible():
            if 0 <= self._row < tw.rowCount():
                return tw.rowHeight(self._row)
            return 0
        try:
            y_vp = self.mapTo(vp, QPoint(self.width() // 2, 1)).y()
            r = tw.rowAt(y_vp)
        except Exception:
            r = -1
        if r < 0 and 0 <= self._row < tw.rowCount():
            return tw.rowHeight(self._row)
        if r < 0:
            return 0
        return tw.rowHeight(r)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_relayout()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_relayout()

    def _schedule_relayout(self) -> None:
        self._relayout_inner()
        self._relayout_timer.stop()
        self._relayout_timer.start(0)

    def _relayout_inner(self) -> None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        sz = self._inner.size()
        if sz.width() <= 0 or sz.height() <= 0:
            return
        if self._horizontal == "right":
            x = max(0, w - sz.width() - self._horizontal_margin)
        else:
            x = max(0, (w - sz.width()) // 2)
        rh = self._effective_row_height()
        h_v = min(h, rh) if rh > 0 else h
        # 与 delegate 上下各 inset 后的文字区中线对齐，略向上修正
        y = max(0, (h_v - sz.height()) // 2 - self._FLUENT_CELL_V_MARGIN)
        self._inner.move(x, y)
        self._inner.raise_()


