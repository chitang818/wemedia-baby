"""
日志显示组件
文件路径：src/ui/components/log_display_widget.py
功能：通用的日志显示组件，支持多日志源监听、彩色日志显示；
     对 publish.user_log 做解析、脱敏、结构化渲染，便于终端用户阅读。
"""

import html
import logging
import re
from typing import List, Optional, Tuple, Any

from src.utils.platform_names import PLATFORM_ID_TO_NAME
from PySide6.QtWidgets import QWidget, QTextEdit, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QObject, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCursor

# 批量刷新间隔（毫秒）：将短时间内的多条日志合并为一次 DOM 操作，减少主线程占用
_LOG_FLUSH_INTERVAL_MS = 80
# 单次累积的最大行数，超出后立即刷新，防止内存无限增长
_LOG_BATCH_MAX_LINES = 30
# 日志区最多保留行数，超出后裁剪旧内容，防止 QTextDocument 无限膨胀导致卡顿
_LOG_MAX_LINES = 600

try:
    from qfluentwidgets import CardWidget, StrongBodyLabel
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    class CardWidget(QWidget): pass
    class StrongBodyLabel(QLabel): pass

# 用户日志行格式：时间 + 消息（由 USER_FORMATTER 产生）
_USER_LOG_LINE_RE = re.compile(r"^(\d{2}:\d{2}:\d{2})\s+(.+)$", re.DOTALL)
# 阶段/步骤前缀
_PHASE_PREPARE = "[准备]"
_PHASE_DETECT = "[检测]"
_PHASE_START = "[启动]"
_PHASE_FLOW = "发布流程"
_STEP_RE = re.compile(r"\[步骤\s*(\d+)/\d+\s+([^\]]+)\]")
# 状态符号
_STATUS_RUNNING = "▶"
_STATUS_OK = "✓"
_STATUS_FAIL = "✗"
# 脱敏：路径、地址、任务ID、URL；保留「文件=xxx」，仅去掉路径部分
_SANITIZE_PATH = re.compile(r"\s*路径=[^\s]+", re.IGNORECASE)
_SANITIZE_ADDR = re.compile(r"\s*地址=https?://[^\s\)]+", re.IGNORECASE)
_SANITIZE_TASK_ID = re.compile(r"\s*任务ID=\d+", re.IGNORECASE)
_SANITIZE_URL_PAREN = re.compile(r"\(https?://[^\)]+\)", re.IGNORECASE)
_SANITIZE_FILE_PATH = re.compile(r"文件=([^\s]+)\s+路径=[^\s]+", re.IGNORECASE)
# 用户日志中的「平台=douyin」等 ID → 中文展示名（与 platform_names 一致）
_PLATFORM_ID_IN_LOG = re.compile(r"平台=([a-zA-Z][a-zA-Z0-9_]*)")


def _parse_user_log_message(body: str) -> Tuple[Optional[str], Optional[str], str]:
    """解析用户日志正文，返回 (阶段/步骤名, 状态, 剩余正文)。"""
    phase_or_step: Optional[str] = None
    status: Optional[str] = None
    rest = body.strip()
    if _PHASE_PREPARE in rest:
        phase_or_step = "准备"
        rest = rest.replace(_PHASE_PREPARE, "", 1).strip()
    elif _PHASE_DETECT in rest:
        phase_or_step = "检测"
        rest = rest.replace(_PHASE_DETECT, "", 1).strip()
    elif _PHASE_START in rest:
        phase_or_step = "启动"
        rest = rest.replace(_PHASE_START, "", 1).strip()
    elif _PHASE_FLOW in rest:
        phase_or_step = "发布流程"
        rest = rest.replace(_PHASE_FLOW, "", 1).strip()
        if rest.startswith("-"):
            rest = rest.lstrip("-").strip()
    else:
        m = _STEP_RE.search(rest)
        if m:
            num, name = m.group(1), m.group(2).strip()
            phase_or_step = f"步骤{num} {name}"
            rest = rest[m.end() :].strip()
    if _STATUS_FAIL in rest:
        status = "fail"
    elif _STATUS_OK in rest:
        status = "ok"
    elif _STATUS_RUNNING in rest:
        status = "running"
    return (phase_or_step, status, rest)


def _sanitize_user_message(text: str, max_reason_len: int = 30) -> str:
    """对用户可见正文脱敏：去掉路径、URL、任务ID，缩短失败原因。"""
    s = text
    s = _SANITIZE_PATH.sub("", s)
    s = _SANITIZE_ADDR.sub("", s)
    s = _SANITIZE_TASK_ID.sub("", s)
    s = _SANITIZE_URL_PAREN.sub("", s)
    s = _SANITIZE_FILE_PATH.sub(r"文件=\1", s)
    if "失败:" in s or "失败：" in s:
        for sep in ("失败:", "失败："):
            if sep in s:
                part = s.split(sep, 1)[-1].strip()
                part = re.sub(r"exception[^\s]*|Error[^\s]*|[\w_]+\.\w+:\s*", "", part, flags=re.IGNORECASE)
                if len(part) > max_reason_len:
                    part = part[: max_reason_len] + "…"
                s = "失败: " + part if part else "失败"
                break
    s = re.sub(r"COVER_SUCCESS_INDICATOR|未配置[^\s]+", "", s, flags=re.IGNORECASE)
    s = _PLATFORM_ID_IN_LOG.sub(
        lambda m: "平台=" + PLATFORM_ID_TO_NAME.get(m.group(1), m.group(1)),
        s,
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s or ""


class GuiLogHandler(logging.Handler, QObject):
    """GUI 日志处理器，将日志信号发射到界面。
    对 publish.user_log 使用简短格式（仅时间+消息），便于用户阅读；其他 logger 使用完整格式（调试用）。
    """
    log_signal = Signal(str, str)  # msg, levelname

    USER_FORMATTER = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    FULL_FORMATTER = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(self.FULL_FORMATTER)

    def emit(self, record):
        if record.name == "publish.user_log":
            msg = self.USER_FORMATTER.format(record)
        else:
            msg = self.FULL_FORMATTER.format(record)
        self.log_signal.emit(msg, record.levelname)


class LogDisplayWidget(QFrame):
    """日志显示组件"""
    
    def __init__(self, title: str = "运行日志", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("PublishLogCard")
        self.log_handler = GuiLogHandler()
        self.listening_loggers = []
        # 批量写入缓冲：将短时间内多条日志合并为一次 DOM 操作，降低主线程压力
        self._pending_html_chunks: List[str] = []
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(_LOG_FLUSH_INTERVAL_MS)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush_pending_html)
        self._setup_ui(title)
        
        # 连接信号
        self.log_handler.log_signal.connect(self.append_log)

    def _setup_ui(self, title_text: str):
        layout = QVBoxLayout(self)
        # 与「任务说明」等底部卡片统一边距与间距
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 头部水平布局
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题
        if FLUENT_WIDGETS_AVAILABLE:
            title_label = StrongBodyLabel(title_text, self)
        else:
            title_label = QLabel(title_text, self)
            title_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        title_label.setObjectName("UnifiedCardTitle")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch(1)
        
        # 清空按钮
        if FLUENT_WIDGETS_AVAILABLE:
            from qfluentwidgets import PushButton, FluentIcon
            self.clear_btn = PushButton(FluentIcon.DELETE, "清空日志", self)
        else:
            from PySide6.QtWidgets import QPushButton
            self.clear_btn = QPushButton("清空日志", self)
            
        self.clear_btn.clicked.connect(self.clear_logs)
        header_layout.addWidget(self.clear_btn)
        
        # 将头部布局加入主布局
        layout.addLayout(header_layout)

        # 两列主体：左侧任务总览 + 右侧当前任务步骤日志
        body_layout = QHBoxLayout()
        body_layout.setSpacing(0)

        # 单列：仅显示日志内容（不再显示任务总览等左侧分区）
        self.log_text_edit = QTextEdit(self)
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setMinimumHeight(72)
        self.log_text_edit.setFont(QFont("Microsoft YaHei", 11))
        self.log_text_edit.setObjectName("LogTextEdit")
        doc = self.log_text_edit.document()
        doc.setDocumentMargin(2)
        doc.setDefaultStyleSheet(
            "p { margin-top: 0; margin-bottom: 1px; line-height: 120%; }"
        )
        body_layout.addWidget(self.log_text_edit, 1)

        layout.addLayout(body_layout)

    def set_task_overview(
        self,
        total: int,
        remaining: int,
        current_index: int,
        task_items: Optional[List[Any]] = None,
    ):
        """兼容旧调用：发布列表仍会传入任务总览数据，这里不再显示，保持空实现即可。"""
        return

    def start_current_task(self):
        """开始当前任务：清空右侧步骤日志区，后续 append_log 仅显示本条任务。"""
        self._flush_timer.stop()
        self._pending_html_chunks.clear()
        self.log_text_edit.clear()

    def start_logging(self, logger_names: List[str], level=logging.INFO):
        """开始监听指定日志"""
        for name in logger_names:
            if name not in self.listening_loggers:
                logger = logging.getLogger(name)
                logger.addHandler(self.log_handler)
                logger.setLevel(level)
                self.listening_loggers.append(name)
    
    def stop_logging(self):
        """停止监听所有日志"""
        for name in self.listening_loggers:
            logger = logging.getLogger(name)
            logger.removeHandler(self.log_handler)
        self.listening_loggers.clear()

    def _render_user_log_line(self, time_str: str, body: str, level: str) -> str:
        """解析并渲染一条 publish.user_log 为 HTML 行（已转义，可安全插入）。"""
        phase_or_step, status, rest = _parse_user_log_message(body)
        sanitized = _sanitize_user_message(rest)
        time_esc = html.escape(time_str)
        step_esc = html.escape(phase_or_step) if phase_or_step else ""
        msg_esc = html.escape(sanitized) if sanitized else ""
        if level == "ERROR" or status == "fail":
            icon, msg_color = "✗", "#c62828"
        elif level == "WARNING":
            icon, msg_color = "⚠", "#e65100"
        elif status == "ok":
            icon, msg_color = "✓", "#2e7d32"
        elif status == "running":
            icon, msg_color = "▶", "#555"
        else:
            icon, msg_color = "·", "#555"
        time_span = f'<span style="color:#888;font-size:11px;">{time_esc}</span>'
        icon_span = f'<span style="color:{msg_color};font-weight:bold;">{icon}</span>'
        step_span = f'<span style="font-weight:bold;color:#333;">{step_esc}</span>' if step_esc else ""
        msg_span = f'<span style="color:{msg_color};">{msg_esc}</span>' if msg_esc else ""
        parts = [time_span, icon_span]
        if step_span:
            parts.append(step_span)
        if msg_span:
            parts.append(msg_span)
        return (
            '<div style="margin:0;padding:0;line-height:120%;">'
            + " ".join(parts)
            + "</div>"
        )

    @Slot(str, str)
    def append_log(self, msg: str, level: str = "INFO"):
        """追加日志。对 publish.user_log 格式做解析、脱敏与结构化渲染；其余仅按级别上色并转义。"""
        m = _USER_LOG_LINE_RE.match(msg.strip())
        if m:
            time_str, body = m.group(1), m.group(2)
            if _PHASE_PREPARE in body or _PHASE_DETECT in body or _PHASE_START in body or _STEP_RE.search(body) or _PHASE_FLOW in body:
                if _PHASE_PREPARE in body and body.strip().startswith(_PHASE_PREPARE) and self.log_text_edit.toPlainText().strip():
                    self.append_html('<div style="border-top:1px solid #eee;margin:2px 0 1px 0;"></div>')
                line_html = self._render_user_log_line(time_str, body, level)
                self.append_html(line_html)
                self._auto_scroll()
                return
        color = None
        if level == "ERROR":
            color = "red"
        elif level == "WARNING":
            color = "#e65100"
        if color:
            safe = html.escape(msg)
            self.append_html(f'<span style="color: {color};">{safe}</span>')
        else:
            self.log_text_edit.append(msg)
        self._auto_scroll()

    def append_text(self, text: str):
        """追加普通文本（走批量缓冲路径，与 append_html 保持一致）"""
        safe = html.escape(str(text))
        self.append_html(f'<span>{safe}</span>')

    def append_warning(self, text: str):
        """追加警告文本 (橙色)，内容已转义"""
        safe = html.escape(str(text))
        self.append_html(f'<br><span style="color: #e65100; font-weight: bold;">⚠ {safe}</span><br>')

    def append_error(self, text: str):
        """追加错误文本 (红色)，内容已转义"""
        safe = html.escape(str(text))
        self.append_html(f'<br><span style="color: #c62828; font-weight: bold;">✗ {safe}</span><br>')

    def append_success(self, text: str):
        """追加成功文本 (绿色)，内容已转义"""
        safe = html.escape(str(text))
        self.append_html(f'<span style="color: #2e7d32; font-weight: bold;">✓ {safe}</span>')

    def append_html(self, html_content: str):
        """追加 HTML 内容（批量缓冲，降低高频调用时的主线程压力）"""
        self._pending_html_chunks.append(html_content)
        if len(self._pending_html_chunks) >= _LOG_BATCH_MAX_LINES:
            # 积累足够多时立即刷新，不再等定时器
            self._flush_pending_html()
        elif not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_pending_html(self):
        """将缓冲中的 HTML 片段一次性写入 QTextEdit"""
        if not self._pending_html_chunks:
            return
        chunks = self._pending_html_chunks
        self._pending_html_chunks = []
        tight_block = QTextBlockFormat()
        tight_block.setTopMargin(0)
        tight_block.setBottomMargin(1)

        cursor = self.log_text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text_edit.setTextCursor(cursor)
        self.log_text_edit.setUpdatesEnabled(False)
        try:
            for chunk in chunks:
                self.log_text_edit.insertHtml(chunk)
                cursor = self.log_text_edit.textCursor()
                cursor.movePosition(QTextCursor.End)
                cursor.insertBlock(tight_block)
                self.log_text_edit.setTextCursor(cursor)
        finally:
            self.log_text_edit.setUpdatesEnabled(True)
        # 超过最大行数时裁剪旧内容，防止 QTextDocument 无限膨胀
        doc = self.log_text_edit.document()
        if doc.blockCount() > _LOG_MAX_LINES:
            trim_cursor = self.log_text_edit.textCursor()
            trim_cursor.movePosition(QTextCursor.Start)
            excess = doc.blockCount() - _LOG_MAX_LINES
            for _ in range(excess):
                trim_cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                trim_cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
            trim_cursor.removeSelectedText()
        self._auto_scroll()

    def clear_logs(self):
        """清空日志内容。任务总览已移至 TaskOverviewCard，此处仅清空日志区。"""
        self._flush_timer.stop()
        self._pending_html_chunks.clear()
        self.log_text_edit.clear()
        if hasattr(self, "_stats_total_label") and self._stats_total_label is not None:
            self._stats_total_label.setText("总计: 0")
        if hasattr(self, "_stats_success_label") and self._stats_success_label is not None:
            self._stats_success_label.setText("成功: 0")
        if hasattr(self, "_stats_failed_label") and self._stats_failed_label is not None:
            self._stats_failed_label.setText("失败: 0")
        if hasattr(self, "_stats_remaining_label") and self._stats_remaining_label is not None:
            self._stats_remaining_label.setText("剩余: 0")
        if hasattr(self, "_progress_bar") and self._progress_bar is not None:
            self._progress_bar.setValue(0)
        if hasattr(self, "_stats_current_label") and self._stats_current_label is not None:
            self._stats_current_label.setText("当前任务：—")
        if hasattr(self, "_task_list_edit") and self._task_list_edit is not None:
            self._task_list_edit.clear()

    def _auto_scroll(self):
        """自动滚动到底部"""
        scrollbar = self.log_text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def closeEvent(self, event):
        """组件关闭时自动停止监听"""
        self.stop_logging()
        super().closeEvent(event)
