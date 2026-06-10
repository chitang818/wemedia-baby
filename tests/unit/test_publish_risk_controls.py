from src.infrastructure.common.pipeline.base_filter import PipelineResult
from src.infrastructure.common.pipeline.publish_pipeline import PublishPipeline
from src.plugins.core.diagnostics.page_dom_diagnostic import redact_sensitive_text
from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.publish_failure_kind import (
    PublishFailureKind,
    classify_publish_failure,
    is_blocking_failure_kind,
)
from src.services.publish.publish_executor import PublishExecutor


def test_publish_failure_kind_classification() -> None:
    assert classify_publish_failure("页面要求重新登录") == PublishFailureKind.AUTH_REQUIRED.value
    assert classify_publish_failure("操作频繁，请稍后重试") == PublishFailureKind.RATE_LIMITED.value
    assert classify_publish_failure("需要完成安全验证码") == PublishFailureKind.RISK_CHALLENGE.value
    assert classify_publish_failure("selector 未找到") == PublishFailureKind.PAGE_CHANGED.value
    assert classify_publish_failure("network timeout") == PublishFailureKind.NETWORK_ERROR.value


def test_publish_results_fill_failure_kind_automatically() -> None:
    plugin_result = PublishResult(success=False, error_message="需要完成安全验证")
    pipeline_result = PipelineResult(success=False, error_message="操作频繁")

    assert plugin_result.failure_kind == PublishFailureKind.RISK_CHALLENGE.value
    assert pipeline_result.failure_kind == PublishFailureKind.RATE_LIMITED.value
    assert is_blocking_failure_kind(plugin_result.failure_kind)
    assert PublishResult(success=True, failure_kind="unknown").failure_kind is None


def test_publish_concurrency_is_clamped_to_two() -> None:
    assert PublishPipeline(max_concurrent=9).max_concurrent == 2
    assert PublishExecutor(user_id=1, max_concurrent=9).max_concurrent == 2


def test_diagnostic_text_redacts_headers_cookies_and_bearer_tokens() -> None:
    raw = (
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
        "Cookie: sessionid=secret-value\n"
        'document.cookie="token=another-secret"\n'
        '"access_token": "abcdef1234567890"'
    )

    redacted = redact_sensitive_text(raw)

    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "secret-value" not in redacted
    assert "another-secret" not in redacted
    assert "abcdef1234567890" not in redacted
    assert "***REDACTED***" in redacted
