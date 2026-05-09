"""
业务异常体系测试
"""
from src.infrastructure.common.exceptions import (
    WeMediaBabyError,
    AuthenticationError,
    PublishError,
    StorageError,
    BrowserError,
    ConfigurationError,
    RateLimitError,
    NetworkError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self):
        for exc_cls in (AuthenticationError, PublishError, StorageError,
                        BrowserError, ConfigurationError, RateLimitError, NetworkError):
            assert issubclass(exc_cls, WeMediaBabyError)
            assert issubclass(exc_cls, Exception)

    def test_catch_by_base(self):
        try:
            raise AuthenticationError("token expired", code="TOKEN_EXPIRED")
        except WeMediaBabyError as e:
            assert e.message == "token expired"
            assert e.code == "TOKEN_EXPIRED"

    def test_detail_kwargs(self):
        err = PublishError("fail", code="P001", platform="douyin", account="test")
        assert err.detail == {"platform": "douyin", "account": "test"}

    def test_str_representation(self):
        err = StorageError("database locked")
        assert str(err) == "database locked"
