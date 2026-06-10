"""Structured failure kinds for publish automation."""

from __future__ import annotations

from enum import Enum


class PublishFailureKind(str, Enum):
    AUTH_REQUIRED = "auth_required"
    RISK_CHALLENGE = "risk_challenge"
    RATE_LIMITED = "rate_limited"
    CONTENT_REJECTED = "content_rejected"
    PAGE_CHANGED = "page_changed"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


BLOCKING_FAILURE_KINDS = frozenset(
    {
        PublishFailureKind.AUTH_REQUIRED.value,
        PublishFailureKind.RISK_CHALLENGE.value,
        PublishFailureKind.RATE_LIMITED.value,
    }
)


_KIND_KEYWORDS: tuple[tuple[PublishFailureKind, tuple[str, ...]], ...] = (
    (
        PublishFailureKind.RISK_CHALLENGE,
        (
            "验证码",
            "验证失败",
            "异常验证",
            "安全验证",
            "账号异常",
            "环境异常",
            "风控",
            "risk",
            "captcha",
        ),
    ),
    (
        PublishFailureKind.RATE_LIMITED,
        (
            "操作频繁",
            "频繁",
            "稍后重试",
            "too many",
            "rate limit",
            "rate_limited",
        ),
    ),
    (
        PublishFailureKind.AUTH_REQUIRED,
        (
            "未登录",
            "重新登录",
            "扫码登录",
            "登录已过期",
            "登录过期",
            "强制登录",
            "cookie失效",
            "cookie 缺失",
            "unauthorized",
            "401",
        ),
    ),
    (
        PublishFailureKind.CONTENT_REJECTED,
        (
            "内容违规",
            "审核",
            "不支持",
            "文件过大",
            "格式错误",
            "格式不支持",
            "禁止发布",
            "rejected",
        ),
    ),
    (
        PublishFailureKind.PAGE_CHANGED,
        (
            "未找到",
            "选择器",
            "页面结构",
            "页面可能改版",
            "按钮不存在",
            "元素不存在",
            "locator",
            "selector",
            "strict mode violation",
        ),
    ),
    (
        PublishFailureKind.NETWORK_ERROR,
        (
            "网络",
            "请求失败",
            "请求超时",
            "timeout",
            "timed out",
            "connection",
            "net::",
            "err_",
            "request failed",
        ),
    ),
)


def normalize_failure_kind(kind: object) -> str | None:
    if kind is None:
        return None
    if isinstance(kind, PublishFailureKind):
        return kind.value
    text = str(kind or "").strip()
    if not text:
        return None
    valid = {item.value for item in PublishFailureKind}
    return text if text in valid else PublishFailureKind.UNKNOWN.value


def classify_publish_failure(message: object) -> str:
    text = str(message or "")
    if not text:
        return PublishFailureKind.UNKNOWN.value
    lower = text.lower()
    for kind, keywords in _KIND_KEYWORDS:
        for keyword in keywords:
            if keyword in text or keyword.lower() in lower:
                return kind.value
    return PublishFailureKind.UNKNOWN.value


def is_blocking_failure_kind(kind: object) -> bool:
    normalized = normalize_failure_kind(kind)
    return bool(normalized and normalized in BLOCKING_FAILURE_KINDS)
