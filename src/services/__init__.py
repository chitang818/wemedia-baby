"""
服务层 (Services Layer)
文件路径：src/services/__init__.py
功能：业务用例编排、应用逻辑

该层整合了原 src/core/application/ 和 src/business/ 的功能

注意：请从子包直接导入所需服务，例如：
  from src.services.account import AccountManagerAsync
  from src.services.account import CookieManager
此包不再维护聚合导出，避免导出列表与子包实际内容持续脱节。
"""
