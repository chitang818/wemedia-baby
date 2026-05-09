"""
账号验证器模块
文件路径：src/services/account/account_verifier.py
功能：批量验证账号Cookie有效性，支持异步HTTP请求验证

重要更新 (2026-01-21):
    已从 requests 同步库迁移到 aiohttp 异步库，
    与 qasync 统一事件循环架构保持一致。
"""

from typing import Dict, List, Optional, Any, Callable
import logging
import asyncio
import aiohttp
import inspect
import random

logger = logging.getLogger(__name__)


class AccountVerifier:
    """账号验证器 - 支持异步批量高效验证"""
    
    def __init__(self, account_manager, max_workers: int = 5):
        """
        初始化账号验证器
        
        Args:
            account_manager: 账号管理器实例
            max_workers: 最大并发数，默认5（避免被限流）
        """
        self.account_manager = account_manager
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session
    
    async def close(self):
        """关闭 aiohttp 会话"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def verify_accounts_batch(
        self, 
        accounts: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, int, Dict[str, Any]], None]] = None
    ) -> Dict[int, Dict[str, Any]]:
        """
        批量验证账号（异步并发）
        
        Args:
            accounts: 账号信息列表 (Dict)
            progress_callback: 进度回调函数 (current, total, account_id, result)
            
        Returns:
            验证结果字典 {account_id: result}
        """
        results = {}
        total = len(accounts)
        completed = [0]  # 使用列表以便在闭包中修改
        
        # 按平台分组账号
        from collections import defaultdict
        platform_groups = defaultdict(list)
        for account in accounts:
            platform = account.get('platform', 'unknown')
            platform_groups[platform].append(account)
        
        self.logger.info(f"开始按平台分组批量验证 {total} 个账号，共 {len(platform_groups)} 个平台")
        for p, accs in platform_groups.items():
            self.logger.info(f"  平台 {p}: {len(accs)} 个账号")
        
        # 每个平台独立的信号量（限制同一平台最多 3 个并发，避免被限流）
        per_platform_concurrency = min(3, self.max_workers)
        
        async def verify_single_account(account: Dict[str, Any], platform_sem: asyncio.Semaphore) -> Dict[str, Any]:
            """验证单个账号（受平台级信号量控制）"""
            async with platform_sem:
                # 添加短随机延迟，避免并发过高
                await asyncio.sleep(random.uniform(0.1, 0.5))
                
                account_id = account.get('id')
                # 获取账号名称（文件夹名），数据库字段通常是 platform_username
                account_name = account.get('platform_username') or account.get('account_name', '')
                
                result = {
                    'account_id': account_id if account_id else -1,
                    'account_name': account_name,
                    'platform': account.get('platform', ''),
                    'is_valid': False,
                    'is_logged_in': False,
                    'username': None,
                    'error': None,
                    'method': 'check'
                }
                
                if not account_id:
                    self.logger.warning(f"账号信息缺失ID: {account}")
                    result['error'] = '账号ID缺失'
                else:
                    # 与「打开浏览器」一致：统一通过 get_account_for_operation + load_account_cookie 加载 Cookie，避免路径不一致导致刷新报 Cookie 不存在
                    account = await self.account_manager.get_account_for_operation(account_id)
                    if not account:
                        result['error'] = '账号不存在或无法解析数据目录'
                        result['method'] = 'file_check'
                    else:
                        account_name = account.get('platform_username') or account.get('account_name', '')
                        result['account_name'] = account_name
                        try:
                            cookie_dict = await self.account_manager.load_account_cookie(
                                account_id, merge_storage_state=True
                            )
                        except Exception as e:
                            self.logger.error(f"加载账号 {account_id} Cookie失败: {e}")
                            cookie_dict = None
                    
                    if not cookie_dict and account:
                        result['error'] = 'Cookie文件不存在，请先双击打开该账号浏览器并登录后再刷新状态'
                        result['method'] = 'file_check'
                    elif account and cookie_dict:
                        if not isinstance(cookie_dict, dict) or not cookie_dict:
                            result['error'] = 'Cookie格式错误'
                            result['method'] = 'file_check'
                        else:
                            from src.services.account.login_status_verifier import verify_login_status
                            try:
                                session = await self._get_session()
                                result = await verify_login_status(
                                    platform=account.get('platform', ''),
                                    cookies=cookie_dict,
                                    account_id=account_id,
                                    account_name=account.get('account_name', '') or account_name,
                                    user_agent=account.get('user_agent'),
                                    http_session=session,
                                    timeout=15,
                                )
                            except Exception as e:
                                result['error'] = f'验证异常: {str(e)}'
                                result['is_valid'] = False
                                result['is_logged_in'] = False
                                result['method'] = 'http'
                                self.logger.error(f"验证账号 {account_id} 异常: {e}", exc_info=True)
                
                # 统一经 AccountManager 写库，与发布列表掉线同步等路径一致；批量验证关闭事件，避免每条都触发账号页全量 reload
                if account_id and account_id != -1:
                    try:
                        status = "online" if result.get("is_logged_in") else "offline"
                        await self.account_manager.update_account_login_status(
                            account_id, status, publish_event=False
                        )
                    except Exception as db_e:
                        self.logger.error(f"后台更新账号 {account_id} 状态失败: {db_e}")

                completed[0] += 1
                if progress_callback:
                    # 使用 call_soon 延迟到下一个事件循环 tick，防止 Qt 信号同步分发
                    # 引发 asyncio task 重入（"Cannot enter into task X while Y is executing"）
                    asyncio.get_event_loop().call_soon(
                        progress_callback, completed[0], total, account_id, result
                    )
                return result
        
        # 为每个平台创建独立的信号量，并行调度所有平台的任务
        all_tasks = []
        for platform, group_accounts in platform_groups.items():
            platform_sem = asyncio.Semaphore(per_platform_concurrency)
            for account in group_accounts:
                all_tasks.append(verify_single_account(account, platform_sem))
        
        # 并发执行所有验证任务
        task_results = await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # 整理结果
        all_accounts_flat = []
        for group_accounts in platform_groups.values():
            all_accounts_flat.extend(group_accounts)
        
        for i, account in enumerate(all_accounts_flat):
            account_id = account.get('id')
            result = task_results[i]
            if isinstance(result, Exception):
                results[account_id] = {
                    'account_id': account_id,
                    'is_valid': False,
                    'is_logged_in': False,
                    'error': f'验证异常: {str(result)}',
                    'method': 'http'
                }
                if account_id and account_id != -1:
                    try:
                        await self.account_manager.update_account_login_status(
                            account_id, "offline", publish_event=False
                        )
                    except Exception as db_e:
                        self.logger.error("异常分支写离线状态失败 account_id=%s: %s", account_id, db_e)
            else:
                if result:
                    results[account_id] = result
        
        # 关闭会话
        await self.close()
        
        self.logger.info(f"批量验证完成，共验证 {len(results)} 个账号")
        return results
