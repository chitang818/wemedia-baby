"""
批量任务重试策略
文件路径：src/pro_features/batch/services/retry_strategy.py

目标：
提供一个可导入、语义合理的重试判断与退避计算器，用于批量发布在网络波动/超时等情况下继续重试。
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional, Callable, Any, List

logger = logging.getLogger(__name__)


class RetryableErrorType(Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"


class NonRetryableErrorType(Enum):
    FILE_NOT_FOUND = "file_not_found"
    COOKIE_EXPIRED = "cookie_expired"
    PERMISSION_DENIED = "permission_denied"
    INVALID_FORMAT = "invalid_format"


class RetryStrategy:
    def __init__(
        self,
        max_retries: int = 3,
        strategy: str = "exponential_backoff",
        intervals: Optional[List[int]] = None,
    ):
        self.max_retries = int(max_retries)
        self.strategy = strategy
        self.intervals = intervals or [5, 10, 20]
        self.logger = logging.getLogger(__name__)

    def should_retry(self, error: Exception, retry_count: int) -> bool:
        if retry_count >= self.max_retries:
            return False

        err = str(error or "").lower()

        # 明确不可重试（例如文件不存在/权限拒绝/cookie 过期）
        non_retryable_keywords = [
            "file not found",
            "cookie expired",
            "permission denied",
            "invalid format",
            "rejected",
            "no such file",
            "账号不存在",
            "用户名或密码错误",
        ]
        if any(k in err for k in non_retryable_keywords):
            return False

        # 可能可重试
        retryable_keywords = [
            "timeout",
            "network",
            "connection",
            "temporary",
            "server error",
            "502",
            "503",
            "504",
            "429",
        ]
        if any(k in err for k in retryable_keywords):
            return True

        # 未命中关键字：保守策略，仅允许首次重试（避免误重试业务类错误）
        return retry_count < 1

    def get_retry_delay(self, retry_count: int) -> int:
        if retry_count < 0:
            retry_count = 0

        if self.strategy == "exponential_backoff":
            if retry_count < len(self.intervals):
                return int(self.intervals[retry_count])
            return int(self.intervals[-1])

        if self.strategy == "fixed":
            return int(self.intervals[0] if self.intervals else 5)

        if self.strategy == "linear":
            base = int(self.intervals[0] if self.intervals else 5)
            return base * (retry_count + 1)

        return 5

    def retry(
        self,
        func: Callable,
        *args,
        error_handler: Optional[Callable[[Exception], None]] = None,
        **kwargs,
    ) -> Any:
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if error_handler:
                    error_handler(e)
                if not self.should_retry(e, attempt):
                    raise
                if attempt < self.max_retries:
                    delay = self.get_retry_delay(attempt)
                    time.sleep(delay)

        if last_error:
            raise last_error
        raise RuntimeError("重试失败：未知错误")


def is_retryable_error(error: Exception) -> bool:
    """快速判断：错误内容是否看起来可以重试。"""
    err = str(error or "").lower()
    non_retryable = [
        "file not found",
        "cookie expired",
        "permission denied",
        "invalid format",
        "rejected",
        "账号不存在",
        "用户名或密码错误",
    ]
    if any(k in err for k in non_retryable):
        return False
    retryable = ["timeout", "network", "connection", "temporary", "server error", "429", "502", "503", "504"]
    return any(k in err for k in retryable)

