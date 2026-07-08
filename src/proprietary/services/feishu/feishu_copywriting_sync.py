"""
飞书文案库同步服务
文件路径：src/proprietary/services/feishu/feishu_copywriting_sync.py
功能：从飞书表格读取文案数据并同步到本地标准文案库

核心逻辑：
1. 读取飞书表格数据（字段映射可配置）
2. 转换为文案库 DTO 格式
3. 复用 CopywritingRepository.bulk_import 进行批量入库
4. 保存同步配置和最后同步时间
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 严格模式：只支持指定的4个中文字段
DEFAULT_FIELD_ALIASES: Dict[str, List[str]] = {
    "work_id": ["作品编号"],
    "short_title": ["作品标题"],
    "description": ["作品描述"],
    "content": ["作品文案"],
}

REQUIRED_FIELDS = ["work_id", "short_title", "description", "content"]


@dataclass
class SyncResult:
    """同步结果"""
    success: bool = False
    message: str = ""
    total_rows: int = 0  # 飞书表格中的总行数（不含表头）
    valid_rows: int = 0  # 有效行数（符合格式要求）
    total_sheets: int = 0 # 扫描到的工作表总数（不含隐藏表）
    valid_sheets: int = 0 # 包含有效文案数据的工作表总数
    inserted: int = 0  # 新增条数
    updated: int = 0  # 更新条数
    failed: int = 0  # 失败条数
    errors: List[str] = field(default_factory=list)
    sync_time: str = ""  # 同步时间 ISO 格式


class FeishuCopywritingSyncService:
    """飞书文案库同步服务"""

    def __init__(self, sheets_client=None):
        if sheets_client is None:
            from .feishu_sheets_client import FeishuSheetsClient
            sheets_client = FeishuSheetsClient()
        self._client = sheets_client

    # ---------- 字段映射自动识别 ----------

    @staticmethod
    def detect_field_mapping(headers: List[str]) -> Dict[str, str]:
        """根据表头自动识别字段映射

        Args:
            headers: 飞书表格表头列表

        Returns:
            映射字典：{文案库字段名: 飞书列名}
        """
        mapping = {}
        header_lower_map = {h.strip(): h for h in headers if h and h.strip()}

        for field_name, aliases in DEFAULT_FIELD_ALIASES.items():
            for alias in aliases:
                alias_lower = alias.strip().lower()
                for h in headers:
                    if h and h.strip().lower() == alias_lower:
                        mapping[field_name] = h.strip()
                        break
                if field_name in mapping:
                    break

        return mapping

    @staticmethod
    def validate_mapping(mapping: Dict[str, str]) -> Tuple[bool, List[str]]:
        """校验字段映射是否满足必填要求

        Returns:
            (是否有效, 缺失的必填字段列表)
        """
        missing = [f for f in REQUIRED_FIELDS if f not in mapping or not mapping[f]]
        return len(missing) == 0, missing

    # ---------- 读取与转换 ----------

    async def fetch_sheet_data(
        self,
        spreadsheet_token: str,
        sheet_id: str,
    ) -> Tuple[List[str], List[List[str]]]:
        """读取飞书表格数据

        Args:
            spreadsheet_token: 表格 token
            sheet_id: 子表 ID

        Returns:
            (headers, rows)
        """
        data = await self._client.read_sheet_all(spreadsheet_token, sheet_id)
        return data.headers, data.rows

    @staticmethod
    def convert_rows_to_items(
        headers: List[str],
        rows: List[List[str]],
        field_mapping: Dict[str, str],
        strict: bool = True,
        category: str = "",
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """将飞书表格行数据转换为文案库 DTO 列表

        Args:
            headers: 表头
            rows: 数据行
            field_mapping: 字段映射 {文案库字段: 飞书列名}
            strict: 是否严格模式（严格模式要求 work_id 和 description 必填）
            category: 强制指定的文案分类（一般是子表名称）

        Returns:
            (items, errors)
        """
        items = []
        errors = []

        col_index = {h: i for i, h in enumerate(headers)}

        target_fields = {
            "work_id": "",
            "short_title": "",
            "description": "",
            "topics": "",
            "content": "",
        }

        for row_idx, row in enumerate(rows, start=2):  # 第1行是表头，数据从第2行开始
            item = {}
            for field, default_val in target_fields.items():
                col_name = field_mapping.get(field)
                if col_name and col_name in col_index:
                    idx = col_index[col_name]
                    value = row[idx] if idx < len(row) else ""
                    item[field] = str(value).strip() if value else ""
                else:
                    item[field] = default_val

            item["category"] = category

            # 如果读取的这行数据（在我们关心的字段内）全都是空的，说明是飞书的空数据行，静默跳过
            is_empty_row = all(not item.get(field) for field in target_fields)
            if is_empty_row:
                continue

            work_id = item.get("work_id", "")
            description = item.get("description", "")

            if strict:
                if not work_id or not description:
                    errors.append(
                        f"第 {row_idx} 行：作品编号或作品描述为空，已跳过。"
                    )
                    continue

                from src.infrastructure.common.copywriting_work_id import (
                    is_valid_copywriting_work_id,
                )
                if not is_valid_copywriting_work_id(work_id):
                    errors.append(
                        f"第 {row_idx} 行：作品编号「{work_id}」格式不正确（须为 1 个大写字母 + 4 位数字，共 5 字符），已跳过。"
                    )
                    continue
            else:
                if not description:
                    errors.append(
                        f"第 {row_idx} 行：作品描述为空，已跳过。"
                    )
                    continue

            items.append(item)

        return items, errors

    # ---------- 同步主流程 ----------

    async def sync_from_feishu(
        self,
        spreadsheet_token: str,
        overwrite_by_work_id: bool = True,
    ) -> SyncResult:
        """从飞书表格全量同步所有子表的文案到本地库

        Args:
            spreadsheet_token: 飞书表格 token
            overwrite_by_work_id: 是否按作品编号覆盖

        Returns:
            SyncResult
        """
        result = SyncResult()

        try:
            if not spreadsheet_token:
                result.message = "表格信息不完整"
                return result

            sheets = await self._client.list_sheets(spreadsheet_token)
            if not sheets:
                result.message = "该表格下没有子表"
                return result

            all_items = []
            
            for sheet in sheets:
                if sheet.is_hidden:
                    continue
                
                result.total_sheets += 1

                headers, rows = await self.fetch_sheet_data(spreadsheet_token, sheet.sheet_id)
                result.total_rows += len(rows)

                if not headers:
                    result.errors.append(f"子表「{sheet.title}」未读取到表头，已跳过")
                    continue

                if not rows:
                    continue

                clean_headers = [str(h or "").strip() for h in headers if str(h or "").strip()]
                exact_headers = {"作品编号", "作品标题", "作品描述", "作品文案"}
                
                if not exact_headers.issubset(set(clean_headers)):
                    missing = exact_headers - set(clean_headers)
                    err_msg = f"子表「{sheet.title}」表头缺失，缺少必需列: {', '.join(missing)}，已跳过。"
                    result.errors.append(err_msg)
                    continue

                mapping = self.detect_field_mapping(headers)
                valid, missing = self.validate_mapping(mapping)
                if not valid:
                    missing_names = "、".join([self._field_display_name(f) for f in missing])
                    result.errors.append(f"子表「{sheet.title}」缺少必填字段映射：{missing_names}，已跳过")
                    continue

                items, parse_errors = self.convert_rows_to_items(
                    headers, rows, mapping, strict=True, category=sheet.title
                )
                
                for error in parse_errors:
                    result.errors.append(f"[子表 {sheet.title}] {error}")
                
                all_items.extend(items)
                if items:
                    result.valid_sheets += 1

            result.valid_rows = len(all_items)

            if not all_items:
                result.message = "所有子表中未解析到任何有效文案数据"
                return result

            from src.infrastructure.storage.repositories.copywriting_repository import (
                CopywritingRepository,
            )

            stats = await CopywritingRepository.bulk_import(
                all_items, overwrite_by_work_id=overwrite_by_work_id, clear_first=True
            )

            result.inserted = stats.get("success", 0) - sum(
                1 for e in stats.get("errors", []) if "更新" in e
            )
            result.failed = stats.get("failed", 0)
            result.errors.extend(stats.get("errors", []))

            result.updated = stats.get("success", 0) - result.inserted
            if result.updated < 0:
                result.updated = 0
                result.inserted = stats.get("success", 0)

            result.success = True
            result.sync_time = datetime.now().isoformat()
            result.message = (
                f"同步完成：共读取 {result.total_rows} 行，"
                f"有效提取 {result.valid_rows} 行，"
                f"成功 {stats.get('success', 0)} 条"
                f"（新增 {result.inserted}、更新 {result.updated}），"
                f"失败 {result.failed} 条。"
            )

        except Exception as e:
            logger.error("飞书文案全量同步失败: %s", e, exc_info=True)
            result.success = False
            result.message = f"同步失败：{e}"
            result.errors.append(str(e))
        finally:
            if self._client:
                await self._client.close()

        return result

    @staticmethod
    def _field_display_name(field: str) -> str:
        """字段名的中文显示"""
        name_map = {
            "work_id": "作品编号",
            "short_title": "作品标题",
            "description": "作品描述",
            "content": "文案内容",
            "topics": "话题",
        }
        return name_map.get(field, field)
