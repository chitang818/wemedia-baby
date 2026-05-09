"""
业务异常体系
功能：定义统一的业务异常基类和具体子类，替代宽泛的 except Exception 吞异常。
关键路径（发布、认证、存储）应抛出具体异常并保留堆栈，便于排查和监控。
"""


class WeMediaBabyError(Exception):
    """业务异常基类——所有可预期的业务错误继承此类。

    使用方式：
        try:
            ...
        except WeMediaBabyError:
            # 已知业务错误，可安全处理
        except Exception:
            # 未知错误，记录堆栈后上报
    """

    def __init__(self, message: str = "", code: str = "", **kwargs):
        self.message = message
        self.code = code
        self.detail = kwargs
        super().__init__(message)


class AuthenticationError(WeMediaBabyError):
    """认证相关异常（登录失败、Token 过期、权限不足等）"""


class PublishError(WeMediaBabyError):
    """发布相关异常（管线失败、平台错误、超时等）"""


class StorageError(WeMediaBabyError):
    """存储相关异常（数据库锁、文件读写失败、COS 错误等）"""


class BrowserError(WeMediaBabyError):
    """浏览器自动化相关异常（启动失败、页面超时、导航错误等）"""


class ConfigurationError(WeMediaBabyError):
    """配置相关异常（缺少必要配置、格式错误等）"""


class RateLimitError(WeMediaBabyError):
    """请求频率超限"""


class NetworkError(WeMediaBabyError):
    """网络请求异常（HTTP 错误、连接超时等）"""
