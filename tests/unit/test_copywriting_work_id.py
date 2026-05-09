"""文案作品编号格式校验单元测试。"""

import pytest

from src.infrastructure.common.copywriting_work_id import is_valid_copywriting_work_id

pytestmark = pytest.mark.unit


class TestIsValidCopywritingWorkId:

    def test_valid_samples(self):
        assert is_valid_copywriting_work_id("A0001") is True
        assert is_valid_copywriting_work_id("B8888") is True
        assert is_valid_copywriting_work_id("Z0000") is True

    def test_rejects_lowercase_letter(self):
        assert is_valid_copywriting_work_id("a0001") is False

    def test_rejects_wrong_length(self):
        assert is_valid_copywriting_work_id("A001") is False
        assert is_valid_copywriting_work_id("A00001") is False

    def test_rejects_non_digit_tail(self):
        assert is_valid_copywriting_work_id("A000x") is False
        assert is_valid_copywriting_work_id("AB000") is False

    def test_strips_whitespace_for_check(self):
        assert is_valid_copywriting_work_id("  A0001  ") is True

    def test_empty(self):
        assert is_valid_copywriting_work_id("") is False
        assert is_valid_copywriting_work_id("   ") is False
