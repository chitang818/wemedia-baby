"""
异步辅助工具
文件路径：src/ui/utils/async_helper.py
功能：提供UI层调用异步函数的辅助工具

重要更新 (2026-01-21):
    项目已迁移到 qasync 统一事件循环架构。
    
    推荐用法：
    1. 在 Widget 中使用 @qasync.asyncSlot() 装饰器处理异步槽函数
    2. 直接使用 asyncio.create_task() 创建异步任务
    
    示例：
    ```python
    from qasync import asyncSlot
    
    class MyWidget(QWidget):
        @asyncSlot()
        async def on_button_clicked(self):
            result = await some_async_operation()
            self.update_ui(result)
    ```
    
    注意：AsyncWorker 类保留用于向后兼容，但新代码应优先使用 @asyncSlot
"""

import asyncio
from typing import Any, Awaitable, Callable, Optional

from PySide6.QtCore import QThread, Signal, QObject, QTimer, Qt
from PySide6.QtWidgets import QDialog
import logging

logger = logging.getLogger(__name__)


def run_async_from_ui_with_finally(
    async_fn: Callable[[], Awaitable[Any]],
    on_done: Callable[[], None],
) -> None:
    """在 UI 事件循环上执行协程，结束后始终在 UI 线程调用 ``on_done``（成功或异常均执行）。

    用于「先 await 写配置再关闭对话框」等场景：避免 ``accept()`` 在写盘任务未完成时就返回。
    ``on_done`` 须短小，仅做关窗、恢复按钮等 UI 操作。
    """
    async def wrapped() -> None:
        try:
            await async_fn()
        except Exception as e:
            logger.exception("run_async_from_ui_with_finally 协程异常: %s", e)
        finally:
            QTimer.singleShot(0, on_done)

    run_async_from_ui(wrapped)


def run_async_from_ui(async_fn: Callable) -> Optional[asyncio.Task]:
    """从 UI 层安全调度异步函数：若事件循环已运行则 create_task，否则 asyncio.run。
    
    Args:
        async_fn: 无参的异步函数（或返回 coroutine 的 callable），如 lambda: update_config()
    
    Returns:
        若在已运行的 loop 中调度则返回 Task，否则返回 None（asyncio.run 会阻塞直到完成）
    """
    try:
        coro = async_fn() if callable(async_fn) else async_fn
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(coro)
        except RuntimeError:
            asyncio.run(coro)
            return None
    except Exception as e:
        logger.exception("run_async_from_ui 异常: %s", e)
        return None


async def await_qdialog_finished(dialog: QDialog, *, window_modal: bool = True) -> int:
    """显示 ``QDialog`` 并异步等待关闭，返回 ``finished(int)`` 的结果码（与 ``exec()`` 返回值含义一致）。

    在 ``@asyncSlot`` / qasync 协程内请**勿**使用 ``dialog.exec()``：会进入 Qt 嵌套模态循环，
    与 asyncio 任务调度冲突，常见报错 ``Cannot enter into task ... while another task ... is being executed``。
    应改用 ``show()`` + 本函数 ``await``。

    Args:
        dialog: 已配置好的对话框实例（尚未 ``show`` / ``exec``）。
        window_modal: 是否设为 ``WindowModal``，默认真以保持与常见 ``exec()`` 交互一致。

    Returns:
        ``QDialog.DialogCode`` 风格的整数码（Accepted / Rejected 等）。
    """
    if window_modal:
        dialog.setWindowModality(Qt.WindowModality.WindowModal)

    loop = asyncio.get_event_loop()
    future = loop.create_future()

    def on_finished(code: int) -> None:
        if not future.done():
            future.set_result(int(code))

    dialog.finished.connect(on_finished)
    dialog.show()
    return await future


class AsyncWorker(QThread):
    """异步/同步工作线程（向后兼容）
    
    ⚠️ 注意：项目已迁移到 qasync 架构。
    新代码建议使用 @qasync.asyncSlot() 装饰器，而不是 AsyncWorker。
    
    此类保留用于：
    - 向后兼容现有代码
    - 需要在独立线程中执行 CPU 密集型任务的场景
    """
    
    finished = Signal(object)  # 完成信号，传递结果
    error = Signal(str)        # 错误信号，传递错误信息
    progress = Signal(int, int, object)  # 进度信号：(current, total, data)
    
    def __init__(self, func: Callable, *args, **kwargs):
        """初始化工作线程
        
        Args:
            func: 要执行的函数（可以是异步 async def 或普通 def）
            *args: 位置参数
            **kwargs: 关键字参数
        """
        import warnings
        warnings.warn(
            "AsyncWorker 已废弃，请使用 @qasync.asyncSlot() 或 asyncio.create_task()",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        """在线程中执行操作"""
        try:
            import asyncio
            import inspect
            
            # 检查是否为异步函数
            if inspect.iscoroutinefunction(self.func):
                # 异步函数处理
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(self.func(*self.args, **self.kwargs))
                    self.finished.emit(result)
                finally:
                    loop.close()
            else:
                # 普通同步函数处理
                result = self.func(*self.args, **self.kwargs)
                self.finished.emit(result)
                
        except Exception as e:
            logger.error(f"工作线程操作失败: {e}", exc_info=True)
            self.error.emit(str(e))


def run_async_task(async_func: Callable, *args, **kwargs) -> asyncio.Task:
    """在 qasync 事件循环中创建异步任务
    
    这是推荐的异步任务创建方式。在 qasync 架构下，
    可以直接在 UI 代码中调用此函数创建异步任务。
    
    Args:
        async_func: 异步函数
        *args: 位置参数
        **kwargs: 关键字参数
    
    Returns:
        asyncio.Task 对象，可用于监控任务状态
    
    Example:
        task = run_async_task(fetch_data, url="https://example.com")
        task.add_done_callback(lambda t: print(t.result()))
    """
    try:
        loop = asyncio.get_running_loop()
        return loop.create_task(async_func(*args, **kwargs))
    except RuntimeError:
        # 如果没有运行中的事件循环，回退到 AsyncWorker 模式
        logger.warning("没有运行中的事件循环，回退到 AsyncWorker 模式")
        raise RuntimeError(
            "run_async_task 必须在 qasync 事件循环中调用。"
            "请确保应用程序通过 qasync.QEventLoop 启动。"
        )


# 保留旧的 run_async 函数用于向后兼容，但标记为废弃
def run_async(async_func: Callable, *args, **kwargs) -> Any:
    """运行异步函数（同步包装）
    
    ⚠️ 已废弃：此函数会阻塞当前线程，不推荐使用。
    请改用 @qasync.asyncSlot() 装饰器或 run_async_task() 函数。
    
    Args:
        async_func: 异步函数
        *args: 位置参数
        **kwargs: 关键字参数
    
    Returns:
        异步函数的返回值
    """
    import warnings
    warnings.warn(
        "run_async() 已废弃，请使用 @qasync.asyncSlot() 或 run_async_task()",
        DeprecationWarning,
        stacklevel=2
    )
    
    try:
        # 尝试获取当前事件循环
        try:
            loop = asyncio.get_running_loop()
            # 如果事件循环正在运行，不能在同一个线程中使用run_until_complete
            # 需要使用线程池执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_run_async_in_thread, async_func, *args, **kwargs)
                return future.result()
        except RuntimeError:
            # 没有运行中的事件循环，可以安全使用
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(async_func(*args, **kwargs))
    except Exception as e:
        logger.error(f"运行异步函数失败: {e}", exc_info=True)
        raise


def _run_async_in_thread(async_func: Callable, *args, **kwargs) -> Any:
    """在线程中运行异步函数（内部辅助函数）"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_func(*args, **kwargs))
    finally:
        loop.close()


