"""
测试数据工厂
提供各类领域对象的默认测试数据，避免各测试文件重复构造。
"""

from __future__ import annotations
from typing import Any


def make_account(**overrides: Any) -> dict:
    """构造账号字典（与 AccountRepositoryAsync._to_dict 输出格式一致）"""
    defaults: dict = {
        "id": 1,
        "user_id": 1,
        "platform": "douyin",
        "account_name": "测试账号",
        "platform_username": "测试账号",
        "cookie_path": "",
        "login_status": "offline",
        "last_login_at": None,
        "profile_folder_name": "profile_test_001",
        "group_id": None,
        "created_at": None,
    }
    defaults.update(overrides)
    return defaults


def make_publish_task(**overrides: Any) -> dict:
    """构造发布任务字典"""
    defaults: dict = {
        "id": 1,
        "user_id": 1,
        "platform": "douyin",
        "platform_username": "测试账号",
        "file_path": "/test/video.mp4",
        "file_type": "video",
        "title": "测试标题",
        "description": "测试描述",
        "scheduled_publish_time": "2025-01-01 10:00",
        "status": "pending",
        "retry_count": 0,
        "error_message": None,
        "created_at": None,
    }
    defaults.update(overrides)
    return defaults


def make_batch_task(**overrides: Any) -> dict:
    """构造批量任务字典"""
    defaults: dict = {
        "id": 1,
        "user_id": 1,
        "name": "测试批量任务",
        "status": "pending",
        "total_count": 0,
        "success_count": 0,
        "failed_count": 0,
        "created_at": None,
    }
    defaults.update(overrides)
    return defaults


def make_cookies(**overrides: Any) -> dict:
    """构造 Cookie 示例数据"""
    defaults: dict = {
        "sessionid": "test_session_id",
        "sessionid_ss": "test_session_ss",
        "sid_tt": "test_sid_tt",
    }
    defaults.update(overrides)
    return defaults


def make_copywriting_item(**overrides: Any) -> dict:
    """构造文案条目字典"""
    defaults: dict = {
        "work_id": "A0001",
        "short_title": "测试标题",
        "description": "测试简介",
        "topics": "#测试 #自动化",
        "content": "测试文案内容",
    }
    defaults.update(overrides)
    return defaults
