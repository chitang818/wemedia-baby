"""
重试策略单元测试
测试 RetryStrategy 各策略的退避时间计算、重试判断逻辑及 is_retryable_error。
"""

import pytest
from unittest.mock import MagicMock, patch

from src.pro_features.batch.services.retry_strategy import (
    RetryStrategy,
    is_retryable_error,
)

pytestmark = pytest.mark.unit


class TestShouldRetry:

    def setup_method(self):
        self.strategy = RetryStrategy(max_retries=3)

    def test_retryable_timeout_error(self):
        err = Exception("connection timeout")
        assert self.strategy.should_retry(err, 0) is True

    def test_retryable_network_error(self):
        err = Exception("network error occurred")
        assert self.strategy.should_retry(err, 0) is True

    def test_retryable_502_error(self):
        err = Exception("502 bad gateway")
        assert self.strategy.should_retry(err, 1) is True

    def test_retryable_503_error(self):
        err = Exception("503 service unavailable")
        assert self.strategy.should_retry(err, 0) is True

    def test_non_retryable_file_not_found(self):
        err = Exception("file not found")
        assert self.strategy.should_retry(err, 0) is False

    def test_non_retryable_cookie_expired(self):
        err = Exception("cookie expired")
        assert self.strategy.should_retry(err, 0) is False

    def test_non_retryable_permission_denied(self):
        err = Exception("permission denied")
        assert self.strategy.should_retry(err, 0) is False

    def test_non_retryable_invalid_format(self):
        err = Exception("invalid format")
        assert self.strategy.should_retry(err, 0) is False

    def test_non_retryable_account_not_exist(self):
        err = Exception("账号不存在")
        assert self.strategy.should_retry(err, 0) is False

    def test_max_retries_exceeded(self):
        err = Exception("timeout")
        assert self.strategy.should_retry(err, 3) is False

    def test_unknown_error_only_first_retry(self):
        err = Exception("some unknown error")
        assert self.strategy.should_retry(err, 0) is True
        assert self.strategy.should_retry(err, 1) is False


class TestGetRetryDelay:

    def test_exponential_backoff_uses_intervals(self):
        strategy = RetryStrategy(max_retries=3, strategy="exponential_backoff", intervals=[5, 10, 20])
        assert strategy.get_retry_delay(0) == 5
        assert strategy.get_retry_delay(1) == 10
        assert strategy.get_retry_delay(2) == 20

    def test_exponential_backoff_clamps_to_last(self):
        strategy = RetryStrategy(max_retries=5, strategy="exponential_backoff", intervals=[5, 10, 20])
        assert strategy.get_retry_delay(10) == 20

    def test_fixed_strategy(self):
        strategy = RetryStrategy(strategy="fixed", intervals=[7])
        assert strategy.get_retry_delay(0) == 7
        assert strategy.get_retry_delay(5) == 7

    def test_linear_strategy(self):
        strategy = RetryStrategy(strategy="linear", intervals=[5])
        assert strategy.get_retry_delay(0) == 5
        assert strategy.get_retry_delay(1) == 10
        assert strategy.get_retry_delay(2) == 15

    def test_negative_retry_count_clamped_to_zero(self):
        strategy = RetryStrategy(strategy="exponential_backoff", intervals=[5, 10])
        assert strategy.get_retry_delay(-1) == 5

    def test_default_strategy_is_exponential(self):
        strategy = RetryStrategy()
        assert strategy.strategy == "exponential_backoff"

    def test_unknown_strategy_returns_default(self):
        strategy = RetryStrategy(strategy="unknown_strategy")
        assert strategy.get_retry_delay(0) == 5


class TestRetryMethod:

    def test_succeeds_on_first_attempt(self):
        strategy = RetryStrategy(max_retries=3)
        func = MagicMock(return_value="success")
        result = strategy.retry(func)
        assert result == "success"
        assert func.call_count == 1

    @patch("time.sleep")
    def test_retries_on_timeout_error(self, mock_sleep):
        strategy = RetryStrategy(max_retries=2, strategy="fixed", intervals=[1])
        call_count = [0]

        def flaky():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("timeout")
            return "done"

        result = strategy.retry(flaky)
        assert result == "done"
        assert call_count[0] == 3

    @patch("time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        strategy = RetryStrategy(max_retries=2, strategy="fixed", intervals=[1])
        func = MagicMock(side_effect=Exception("timeout"))
        with pytest.raises(Exception, match="timeout"):
            strategy.retry(func)

    def test_does_not_retry_non_retryable_error(self):
        strategy = RetryStrategy(max_retries=3)
        func = MagicMock(side_effect=Exception("file not found"))
        with pytest.raises(Exception, match="file not found"):
            strategy.retry(func)
        assert func.call_count == 1

    @patch("time.sleep")
    def test_error_handler_called(self, mock_sleep):
        strategy = RetryStrategy(max_retries=1, strategy="fixed", intervals=[1])
        handler = MagicMock()
        func = MagicMock(side_effect=Exception("timeout"))
        with pytest.raises(Exception):
            strategy.retry(func, error_handler=handler)
        assert handler.called


class TestIsRetryableError:

    def test_timeout_is_retryable(self):
        assert is_retryable_error(Exception("request timeout")) is True

    def test_network_is_retryable(self):
        assert is_retryable_error(Exception("network error")) is True

    def test_429_is_retryable(self):
        assert is_retryable_error(Exception("429 too many requests")) is True

    def test_file_not_found_not_retryable(self):
        assert is_retryable_error(Exception("file not found")) is False

    def test_cookie_expired_not_retryable(self):
        assert is_retryable_error(Exception("cookie expired")) is False

    def test_generic_error_not_retryable(self):
        assert is_retryable_error(Exception("some other error")) is False

    def test_none_error_not_retryable(self):
        assert is_retryable_error(Exception("")) is False
