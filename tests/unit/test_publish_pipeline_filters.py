"""
发布管线过滤器单元测试
覆盖：PermissionCheckFilterAsync 的缓存逻辑、限流、降级放行
"""
import time
import tempfile
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.publish.pipeline.filters.permission_check_filter_async import (
    _get_cached_publish_check,
    _set_publish_check_cache,
    _PUBLISH_CHECK_CACHE,
    _CACHE_MAX_SIZE,
    _maybe_cleanup_cache,
    _evict_oldest_if_full,
    PermissionCheckFilterAsync,
)
from src.infrastructure.common.pipeline.base_filter import BaseFilter, PublishContext, PublishRequest
from src.infrastructure.common.pipeline.publish_pipeline import PublishPipeline
from src.infrastructure.common.pipeline.filters.execution_filter import PublishExecutionFilter
from src.services.publish.pipeline.pipeline_factory_async import PipelineFactoryAsync
from src.services.publish.pipeline.filters.account_load_filter_async import AccountLoadFilterAsync
from src.services.publish.pipeline.filters.media_validate_filter_async import MediaValidateFilterAsync
from src.services.publish.pipeline.filters.record_save_filter_async import RecordSaveFilterAsync


@pytest.fixture(autouse=True)
def clear_cache():
    """每个测试前清空缓存。"""
    _PUBLISH_CHECK_CACHE.clear()
    yield
    _PUBLISH_CHECK_CACHE.clear()


class TestPublishCheckCache:
    """publish_check 缓存逻辑测试"""

    def test_cache_miss_returns_none(self):
        assert _get_cached_publish_check("tok", "douyin", False) is None

    def test_cache_hit_returns_true(self):
        _set_publish_check_cache("tok", "douyin", False, True)
        assert _get_cached_publish_check("tok", "douyin", False) is True

    def test_denied_result_not_cached(self):
        _set_publish_check_cache("tok", "douyin", False, False)
        assert _get_cached_publish_check("tok", "douyin", False) is None

    def test_expired_entry_evicted(self):
        key = ("tok", "douyin", False)
        _PUBLISH_CHECK_CACHE[key] = (True, time.monotonic() - 10)
        assert _get_cached_publish_check("tok", "douyin", False) is None
        assert key not in _PUBLISH_CHECK_CACHE

    def test_max_size_eviction(self):
        for i in range(_CACHE_MAX_SIZE + 10):
            _set_publish_check_cache(f"tok{i}", "p", False, True)
        assert len(_PUBLISH_CHECK_CACHE) <= _CACHE_MAX_SIZE


class TestPermissionCheckFilterAsync:
    """PermissionCheckFilterAsync 过滤器测试"""

    @pytest.mark.asyncio
    async def test_subscription_disabled_passes(self):
        """订阅功能未启用时应放行。"""
        f = PermissionCheckFilterAsync(permission_controller=None)
        ctx = MagicMock()
        with patch("src.services.publish.pipeline.filters.permission_check_filter_async.FeatureFlags") as MockFF:
            MockFF.is_feature_enabled.return_value = False
            # 需要 mock 掉 import
            with patch.dict("sys.modules", {"config.feature_flags": MagicMock(FeatureFlags=MockFF)}):
                result = await f.process(ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_permission_controller_passes(self):
        """无权限控制器时应放行（开源版场景）。"""
        f = PermissionCheckFilterAsync(permission_controller=None)
        ctx = MagicMock()
        # FeatureFlags 启用但控制器为 None
        mock_ff = MagicMock()
        mock_ff.is_feature_enabled.return_value = True
        with patch.dict("sys.modules", {"config.feature_flags": MagicMock(FeatureFlags=mock_ff)}):
            result = await f.process(ctx)
        assert result is True


class _FailingExecutionFilter(BaseFilter):
    allow_failure_finalizers = True

    async def process(self, context: PublishContext) -> bool:
        self.set_error("publish failed")
        return False


class _FailingPreconditionFilter(BaseFilter):
    async def process(self, context: PublishContext) -> bool:
        self.set_error("precondition failed")
        return False


class _RecordingFinalizerFilter(BaseFilter):
    run_after_failure = True

    def __init__(self):
        super().__init__()
        self.called = False
        self.error_seen = None

    async def process(self, context: PublishContext) -> bool:
        self.called = True
        self.error_seen = context.error_message
        return True


def _request() -> PublishRequest:
    return PublishRequest(
        user_id=1,
        account_name="account",
        platform="douyin",
        file_path="video.mp4",
    )


class TestPublishPipelineFailureFinalizers:
    @pytest.mark.asyncio
    async def test_publish_failure_runs_record_finalizer(self):
        pipeline = PublishPipeline(max_concurrent=1)
        finalizer = _RecordingFinalizerFilter()
        pipeline.add_filter(_FailingExecutionFilter())
        pipeline.add_filter(finalizer)

        result = (await pipeline.execute(_request()))[0]

        assert result.success is False
        assert result.error_message == "publish failed"
        assert finalizer.called is True
        assert finalizer.error_seen == "publish failed"

    @pytest.mark.asyncio
    async def test_precondition_failure_does_not_run_record_finalizer(self):
        pipeline = PublishPipeline(max_concurrent=1)
        finalizer = _RecordingFinalizerFilter()
        pipeline.add_filter(_FailingPreconditionFilter())
        pipeline.add_filter(finalizer)

        result = (await pipeline.execute(_request()))[0]

        assert result.success is False
        assert result.error_message == "precondition failed"
        assert finalizer.called is False


class TestPipelineFactoryAsync:
    @pytest.mark.asyncio
    async def test_factory_matches_main_pipeline_filter_order_and_limit(self):
        pipeline = await PipelineFactoryAsync.create_pipeline(
            user_id=1,
            account_manager=MagicMock(),
            permission_controller=MagicMock(),
            media_validator=MagicMock(),
        )

        assert getattr(pipeline.semaphore, "_value", None) == 3
        assert [type(f) for f in pipeline.filters] == [
            PermissionCheckFilterAsync,
            MediaValidateFilterAsync,
            AccountLoadFilterAsync,
            PublishExecutionFilter,
            RecordSaveFilterAsync,
        ]


class TestMediaValidateFilterAsync:
    def _validator(self):
        validator = MagicMock()
        validator.validate_format.return_value = True
        validator.validate_size.return_value = True
        return validator

    @pytest.mark.asyncio
    async def test_image_folder_marker_composite_path_passes(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "pack"
            folder.mkdir()
            img1 = folder / "a.jpg"
            img2 = folder / "b.png"
            img1.write_bytes(b"a")
            img2.write_bytes(b"b")
            composite = f"__FOLDER__:{folder},{img1},{img2}"
            validator = self._validator()
            filt = MediaValidateFilterAsync(validator)
            ctx = _publish_context(
                file_path=composite,
                file_type="image",
                publish_type="image",
            )

            ok = await filt.process(ctx)

            assert ok is True
            assert validator.validate_format.call_count == 2
            validator.validate_format.assert_any_call(str(img1), "image", "xiaohongshu")
            validator.validate_format.assert_any_call(str(img2), "image", "xiaohongshu")

    @pytest.mark.asyncio
    async def test_image_comma_paths_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img1 = root / "a.jpg"
            img2 = root / "b.webp"
            img1.write_bytes(b"a")
            img2.write_bytes(b"b")
            validator = self._validator()
            filt = MediaValidateFilterAsync(validator)
            ctx = _publish_context(
                file_path=f"{img1},{img2}",
                file_type="image",
                publish_type="image",
            )

            ok = await filt.process(ctx)

            assert ok is True
            assert validator.validate_size.call_count == 2

    @pytest.mark.asyncio
    async def test_image_composite_reports_missing_partial_file(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "pack"
            folder.mkdir()
            img1 = folder / "a.jpg"
            missing = folder / "missing.png"
            img1.write_bytes(b"a")
            filt = MediaValidateFilterAsync(self._validator())
            ctx = _publish_context(
                file_path=f"__FOLDER__:{folder},{img1},{missing}",
                file_type="image",
                publish_type="image",
            )

            ok = await filt.process(ctx)

            assert ok is False
            assert "部分图片不存在" in filt.get_error()
            assert "missing.png" in filt.get_error()

    @pytest.mark.asyncio
    async def test_image_folder_marker_without_images_fails(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "pack"
            folder.mkdir()
            filt = MediaValidateFilterAsync(self._validator())
            ctx = _publish_context(
                file_path=f"__FOLDER__:{folder}",
                file_type="image",
                publish_type="image",
            )

            ok = await filt.process(ctx)

            assert ok is False
            assert filt.get_error() == "未指定发布图片路径"

    @pytest.mark.asyncio
    async def test_video_single_file_still_uses_video_validation(self):
        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "v.mp4"
            video.write_bytes(b"video")
            validator = self._validator()
            filt = MediaValidateFilterAsync(validator)
            ctx = _publish_context(
                file_path=str(video),
                file_type="video",
                publish_type="video",
            )

            ok = await filt.process(ctx)

            assert ok is True
            validator.validate_format.assert_called_once_with(
                str(video), "video", "xiaohongshu"
            )
            validator.validate_size.assert_called_once_with(
                str(video), "video", "xiaohongshu"
            )


def _publish_context(**kwargs) -> PublishContext:
    base = dict(
        user_id=1,
        account_name="tester",
        platform="xiaohongshu",
        file_path="video.mp4",
    )
    base.update(kwargs)
    return PublishContext(**base)


class TestRecordSaveFilterAsync:
    @pytest.mark.asyncio
    async def test_updates_existing_record_on_failure_instead_of_create(self):
        repo = MagicMock()
        repo.create = AsyncMock()
        repo.update_status = AsyncMock(return_value=True)
        filt = RecordSaveFilterAsync(publish_record_repository=repo)
        ctx = _publish_context(publish_record_id=679, error_message="步骤失败")

        ok = await filt.process(ctx)

        assert ok is True
        repo.create.assert_not_called()
        repo.update_status.assert_awaited_once_with(
            record_id=679,
            status="failed",
            error_message="步骤失败",
        )

    @pytest.mark.asyncio
    async def test_creates_new_record_when_no_publish_record_id(self):
        repo = MagicMock()
        repo.create = AsyncMock(return_value=683)
        repo.update_status = AsyncMock(return_value=True)
        filt = RecordSaveFilterAsync(publish_record_repository=repo)
        ctx = _publish_context(error_message="步骤失败")

        ok = await filt.process(ctx)

        assert ok is True
        repo.create.assert_awaited_once()
        repo.update_status.assert_awaited_once_with(
            record_id=683,
            status="failed",
            error_message="步骤失败",
        )
