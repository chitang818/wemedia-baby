"""
Excel 文案导入模块单元测试
测试 parse_excel 的正常解析、缺失列报错、空行跳过等场景。
"""

from __future__ import annotations

import pytest
from pathlib import Path
from openpyxl import Workbook

from src.infrastructure.common.excel_copywriting_importer import (
    parse_excel,
    REQUIRED_HEADERS,
    OPTIONAL_HEADERS,
)

pytestmark = pytest.mark.unit


def _write_workbook(path: Path, headers: list, rows: list) -> str:
    """辅助：写一个 xlsx 并返回路径字符串"""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(str(path))
    return str(path)


class TestParseExcelNormal:

    def test_basic_parse(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号", "文案内容"],
            [["A0001", "这是第一条文案"]],
        )
        result = parse_excel(path)
        assert result["total"] == 1
        assert result["success"] == 1
        assert result["failed"] == 0
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["work_id"] == "A0001"
        assert item["content"] == "这是第一条文案"

    def test_optional_columns_filled(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号", "文案内容", "作品标题", "作品简介", "话题"],
            [["B0002", "文案内容", "短标题", "简介文字", "#标签1 #标签2"]],
        )
        result = parse_excel(path)
        item = result["items"][0]
        assert item["short_title"] == "短标题"
        assert item["description"] == "简介文字"
        assert item["topics"] == "#标签1 #标签2"

    def test_multiple_rows(self, tmp_path):
        rows = [[f"W{i:04d}", f"文案{i}"] for i in range(5)]
        path = _write_workbook(tmp_path / "test.xlsx", ["作品编号", "文案内容"], rows)
        result = parse_excel(path)
        assert result["total"] == 5
        assert result["success"] == 5

    def test_empty_row_skipped(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号", "文案内容"],
            [["A0001", "文案"], [None, None], ["A0002", "文案2"]],
        )
        result = parse_excel(path)
        assert result["total"] == 2
        assert result["success"] == 2

    def test_missing_work_id_counted_as_failed(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号", "文案内容"],
            [["", "有内容但没有编号"]],
        )
        result = parse_excel(path)
        assert result["failed"] == 1
        assert len(result["errors"]) == 1

    def test_missing_content_counted_as_failed(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号", "文案内容"],
            [["A0001", ""]],
        )
        result = parse_excel(path)
        assert result["failed"] == 1

    def test_optional_columns_default_empty(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号", "文案内容"],
            [["A0001", "文案"]],
        )
        result = parse_excel(path)
        item = result["items"][0]
        assert item["short_title"] == ""
        assert item["description"] == ""
        assert item["topics"] == ""

    def test_invalid_work_id_skipped_with_error(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号", "文案内容"],
            [["a0001", "文案小写编号"], ["A0002", "合法第二行"]],
        )
        result = parse_excel(path)
        assert result["total"] == 2
        assert result["success"] == 1
        assert result["failed"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["work_id"] == "A0002"
        assert any("a0001" in e for e in result["errors"])


class TestParseExcelErrors:

    def test_missing_required_header_raises(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号"],  # 缺少「文案内容」
            [["A0001"]],
        )
        with pytest.raises(ValueError, match="表头缺失"):
            parse_excel(path)

    def test_completely_missing_headers_raises(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["无关列1", "无关列2"],
            [["val1", "val2"]],
        )
        with pytest.raises(ValueError):
            parse_excel(path)

    def test_empty_sheet_returns_zero(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号", "文案内容"],
            [],
        )
        result = parse_excel(path)
        assert result["total"] == 0
        assert result["success"] == 0

    def test_return_structure_has_all_keys(self, tmp_path):
        path = _write_workbook(
            tmp_path / "test.xlsx",
            ["作品编号", "文案内容"],
            [["A0001", "文案"]],
        )
        result = parse_excel(path)
        assert "items" in result
        assert "total" in result
        assert "success" in result
        assert "failed" in result
        assert "errors" in result
