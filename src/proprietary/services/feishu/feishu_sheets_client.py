"""
飞书表格客户端
文件路径：src/proprietary/services/feishu/feishu_sheets_client.py
功能：封装飞书电子表格 API，提供表格结构查询、数据读取等能力

API 文档：https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet/query
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import aiohttp

from .feishu_auth_service import FeishuAuthService

logger = logging.getLogger(__name__)

SHEETS_API_BASE = "https://open.feishu.cn/open-apis/sheets/v2"
DRIVE_API_BASE = "https://open.feishu.cn/open-apis/drive/v1"


@dataclass
class SheetInfo:
    """子表信息"""
    sheet_id: str
    title: str
    row_count: int = 0
    column_count: int = 0
    index: int = 0
    is_hidden: bool = False


@dataclass
class SpreadsheetInfo:
    """电子表格信息"""
    token: str
    title: str
    url: str = ""
    sheets: List[SheetInfo] = field(default_factory=list)


@dataclass
class SheetData:
    """表格数据"""
    sheet_id: str
    sheet_name: str
    range: str = ""
    headers: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)

    def to_dicts(self) -> List[Dict[str, Any]]:
        """转换为字典列表（每行是 {列名: 值}）"""
        result = []
        for row in self.rows:
            item = {}
            for i, header in enumerate(self.headers):
                item[header] = row[i] if i < len(row) else ""
            result.append(item)
        return result


class FeishuSheetsClient:
    """飞书表格客户端

    基于飞书电子表格 OpenAPI v3，提供数据读取能力。
    使用 user_access_token 访问用户有权限的表格。
    """

    def __init__(self, auth_service: Optional[FeishuAuthService] = None):
        self._auth = auth_service or FeishuAuthService.get_instance()
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_headers(self) -> Dict[str, str]:
        token = await self._auth.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发起 API 请求"""
        session = self._get_session()
        headers = await self._get_headers()

        async with session.request(
            method, url, params=params, json=json_data, headers=headers
        ) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception as e:
                text = await resp.text()
                logger.error("飞书 API 返回非 JSON 格式 [%s %s]: status=%s, content=%s", method, url, resp.status, text)
                raise RuntimeError(f"飞书 API 返回格式错误：{resp.status} - {text[:200]}")

            code = data.get("code", -1)
            if code != 0:
                msg = data.get("msg", "未知错误")
                logger.error("飞书 API 调用失败 [%s %s]: code=%s, msg=%s", method, url, code, msg)
                raise RuntimeError(f"飞书 API 调用失败：{msg} (code={code})")
            return data

    # ---------- 链接解析 ----------

    @staticmethod
    def parse_spreadsheet_token(url: str) -> str:
        """从飞书表格 URL 中提取 spreadsheet_token

        支持的 URL 格式：
        - https://xxx.feishu.cn/sheets/xxx
        - https://xxx.feishu.cn/spreadsheets/xxx
        - 直接传 token
        """
        url = url.strip()
        if not url:
            return ""

        # 直接传入了 token (没有斜杠)
        if "/" not in url and len(url) > 10:
            return url.split("?")[0].split("#")[0]

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path = parsed.path

            parts = [p for p in path.split("/") if p]

            # 正常解析 /sheets/ 或 /spreadsheets/ 后的字符串
            for i, part in enumerate(parts):
                if part in ("sheets", "spreadsheets") and i + 1 < len(parts):
                    token = parts[i + 1]
                    token = token.split("?")[0].split("#")[0]
                    if token and len(token) > 5:
                        return token

            # 兼容老逻辑：在路径中强行寻找 sht 开头的
            for part in parts:
                clean_part = part.split("?")[0].split("#")[0]
                if clean_part.startswith("sht") and len(clean_part) > 5:
                    return clean_part
        except Exception:
            pass

        return ""

    # ---------- 工作簿信息 ----------

    async def get_spreadsheet(self, spreadsheet_token: str) -> SpreadsheetInfo:
        """获取电子表格元信息（不含子表列表）"""
        url = f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}"
        logger.info("飞书 API 请求：GET %s", url)
        data = await self._request("GET", url)
        sheet_data = data.get("data", {}).get("spreadsheet", {})
        return SpreadsheetInfo(
            token=spreadsheet_token,
            title=sheet_data.get("title", ""),
            url=sheet_data.get("url", ""),
        )

    async def list_sheets(self, spreadsheet_token: str) -> List[SheetInfo]:
        """获取所有子表列表"""
        url = f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
        data = await self._request("GET", url)
        sheets_data = data.get("data", {}).get("sheets", []) or []
        result = []
        for s in sheets_data:
            result.append(
                SheetInfo(
                    sheet_id=s.get("sheet_id", ""),
                    title=s.get("title", ""),
                    row_count=s.get("grid_properties", {}).get("row_count", 0),
                    column_count=s.get("grid_properties", {}).get("column_count", 0),
                    index=s.get("index", 0),
                    is_hidden=s.get("hidden", False),
                )
            )
        return result

    # ---------- 数据读取 ----------

    async def read_range(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        range_str: str,
        value_render_option: str = "ToString",
    ) -> SheetData:
        """读取指定范围的数据

        Args:
            spreadsheet_token: 表格 token
            sheet_id: 子表 ID
            range_str: A1 范围，如 "A1:F100"
            value_render_option: 值渲染方式
                - FormattedValue: 带格式的显示值（默认）
                - ToString: 全部转字符串
                - Formula: 公式原文

        Returns:
            SheetData 对象
        """
        url = (
            f"{SHEETS_API_BASE}/spreadsheets/{spreadsheet_token}"
            f"/values/{sheet_id}!{quote(range_str)}"
        )
        params = {"valueRenderOption": value_render_option}
        data = await self._request("GET", url, params=params)

        value_range = data.get("data", {}).get("valueRange", {})
        values = value_range.get("values", []) or []

        headers = []
        rows = []
        if values:
            headers = [str(v) if v is not None else "" for v in values[0]]
            for row in values[1:]:
                cleaned = [str(v) if v is not None else "" for v in row]
                while len(cleaned) < len(headers):
                    cleaned.append("")
                rows.append(cleaned)

        return SheetData(
            sheet_id=sheet_id,
            sheet_name="",
            range=value_range.get("range", range_str),
            headers=headers,
            rows=rows,
        )

    async def read_sheet_all(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        sheet_info: Optional[SheetInfo] = None,
    ) -> SheetData:
        """读取整个子表的数据

        Args:
            spreadsheet_token: 表格 token
            sheet_id: 子表 ID
            sheet_info: 子表信息（可选，传了就不重新查询）

        Returns:
            SheetData 对象
        """
        if sheet_info is None:
            sheets = await self.list_sheets(spreadsheet_token)
            target = next((s for s in sheets if s.sheet_id == sheet_id), None)
            if not target:
                raise RuntimeError(f"找不到子表：{sheet_id}")
            sheet_info = target

        col_count = sheet_info.column_count or 100
        row_count = sheet_info.row_count or 1000

        last_col = self._column_index_to_letter(col_count)
        range_str = f"A1:{last_col}{row_count}"

        return await self.read_range(spreadsheet_token, sheet_id, range_str)

    @staticmethod
    def _column_index_to_letter(index: int) -> str:
        """列号转字母（1-based，1=A, 26=Z, 27=AA）"""
        result = ""
        index = int(index)
        while index > 0:
            index -= 1
            result = chr(ord("A") + (index % 26)) + result
            index //= 26
        return result or "A"

    # ---------- 云空间搜索（可选能力，视权限而定） ----------

    async def search_files(
        self,
        query: str = "",
        doc_type: str = "sheet",
        page_size: int = 20,
        page_token: str = "",
    ) -> Tuple[List[Dict[str, Any]], str]:
        """搜索云空间中的文件（需要 drive 权限）

        Args:
            query: 搜索关键词
            doc_type: 文档类型，sheet / docx / bitable 等
            page_size: 每页数量
            page_token: 分页 token

        Returns:
            (文件列表, 下一页 token)
        """
        url = f"{DRIVE_API_BASE}/files/search"
        params = {
            "query": query,
            "doc_type": doc_type,
            "page_size": page_size,
        }
        if page_token:
            params["page_token"] = page_token

        data = await self._request("POST", url, json_data=params)
        files = data.get("data", {}).get("files", []) or []
        next_token = data.get("data", {}).get("page_token", "")
        return files, next_token
