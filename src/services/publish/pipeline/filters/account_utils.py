"""
账号加载过滤器共用工具
文件路径：src/services/publish/pipeline/filters/account_utils.py
功能：按 account_name 从账号列表中查找账号，供 account_load_filter 与 account_load_filter_async 共用
"""
from typing import List, Dict, Any, Optional


def find_account_by_name(accounts: List[Dict[str, Any]], account_name: str) -> Optional[Dict[str, Any]]:
    """从账号列表中按 account_name 查找第一个匹配的账号。

    Args:
        accounts: 账号字典列表（如 get_accounts 返回）
        account_name: 要匹配的账号名

    Returns:
        匹配的账号字典，未找到返回 None
    """
    for acc in accounts:
        if acc.get("account_name") == account_name:
            return acc
    return None
