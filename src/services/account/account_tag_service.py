"""
账号标签服务
文件路径：src/services/account/account_tag_service.py
功能：账号标签的业务逻辑（增删改查、账号关联）
"""

import logging
from typing import List, Dict, Any

from tortoise.exceptions import DoesNotExist
from src.infrastructure.storage.orm_models.account_tag import AccountTag
from src.infrastructure.storage.orm_models.platform_account import PlatformAccount
from src.infrastructure.storage.orm_models.account_group import AccountGroup

logger = logging.getLogger(__name__)

class AccountTagService:
    """账号标签服务"""

    async def get_tags(self) -> List[Dict[str, Any]]:
        """获取所有账号标签列表"""
        try:
            tags = await AccountTag.all().prefetch_related("accounts", "groups")
            result = []
            for tag in tags:
                accounts = await tag.accounts.all()
                groups = await tag.groups.all()

                # 兼容旧数据：没有 tag_type 时按已关联对象推断；都没有则默认账号标签
                tag_type = getattr(tag, "tag_type", None)
                if not tag_type:
                    if groups and not accounts:
                        tag_type = "group"
                    else:
                        tag_type = "account"
                
                result.append({
                    "id": tag.id,
                    "name": tag.name,
                    "tag_type": tag_type,
                    "accounts": [
                        {
                            "id": a.id,
                            "platform_username": a.platform_username,
                            "platform": a.platform
                        } for a in accounts
                    ],
                    "groups": [
                        {
                            "id": g.id,
                            "group_name": g.group_name
                        } for g in groups
                    ],
                    "account_count": len(accounts),
                    "group_count": len(groups)
                })
            return result
        except Exception as e:
            logger.error(f"获取账号标签失败: {e}")
            return []

    async def create_tag(self, user_id: int, name: str, tag_type: str = "account") -> int:
        """创建账号标签"""
        try:
            # 检查同名
            exists = await AccountTag.filter(name=name, user_id=user_id).exists()
            if exists:
                raise ValueError(f"标签 '{name}' 已存在")

            tag_type = (tag_type or "account").strip().lower()
            if tag_type not in ("account", "group"):
                tag_type = "account"

            tag = await AccountTag.create(user_id=user_id, name=name, tag_type=tag_type)
            return tag.id
        except Exception as e:
            logger.error(f"创建账号标签失败: {e}")
            raise

    async def update_tag(self, tag_id: int, name: str) -> bool:
        """更新标签名称"""
        try:
            tag = await AccountTag.get_or_none(id=tag_id)
            if not tag:
                raise ValueError("标签不存在")
                
            # 检查同名
            exists = await AccountTag.filter(name=name, id__not=tag_id).exists()
            if exists:
                raise ValueError(f"标签 '{name}' 已存在")
                
            tag.name = name
            await tag.save()
            return True
        except Exception as e:
            logger.error(f"更新账号标签失败: {e}")
            raise

    async def delete_tag(self, tag_id: int) -> bool:
        """删除标签（解除关联并删除记录）"""
        try:
            tag = await AccountTag.get_or_none(id=tag_id)
            if not tag:
                return False
            # Tortoise M2M 级联关系处理：如果定义了 CASCADE 或者默认，delete 会清理中间表
            await tag.delete()
            return True
        except Exception as e:
            logger.error(f"删除账号标签失败: {e}")
            raise

    async def add_account_to_tag(self, tag_id: int, account_id: int) -> bool:
        """添加账号到标签"""
        try:
            tag = await AccountTag.get_or_none(id=tag_id)
            account = await PlatformAccount.get_or_none(id=account_id)
            if not tag or not account:
                raise ValueError("标签或账号不存在")

            # 规则：一个标签只能绑定账号或账号组之一
            try:
                existing_groups = await tag.groups.all()
            except Exception:
                existing_groups = []
            if existing_groups:
                raise ValueError("该标签已绑定账号组，不能再绑定账号（一个标签只能包含账号或账号组其中一种）")
                
            await tag.accounts.add(account)
            return True
        except Exception as e:
            logger.error(f"添加账号到标签失败: {e}")
            raise

    async def remove_account_from_tag(self, tag_id: int, account_id: int) -> bool:
        """从标签移除账号"""
        try:
            tag = await AccountTag.get_or_none(id=tag_id)
            account = await PlatformAccount.get_or_none(id=account_id)
            if not tag or not account:
                return False
                
            await tag.accounts.remove(account)
            return True
        except Exception as e:
            logger.error(f"从标签移除账号失败: {e}")
            raise

    async def add_group_to_tag(self, tag_id: int, group_id: int) -> bool:
        """添加账号组到标签"""
        try:
            tag = await AccountTag.get_or_none(id=tag_id)
            group = await AccountGroup.get_or_none(id=group_id)
            if not tag or not group:
                raise ValueError("标签或账号组不存在")

            # 规则：一个标签只能绑定账号或账号组之一
            try:
                existing_accounts = await tag.accounts.all()
            except Exception:
                existing_accounts = []
            if existing_accounts:
                raise ValueError("该标签已绑定账号，不能再绑定账号组（一个标签只能包含账号或账号组其中一种）")
                
            await tag.groups.add(group)
            return True
        except Exception as e:
            logger.error(f"添加账号组到标签失败: {e}")
            raise

    async def remove_group_from_tag(self, tag_id: int, group_id: int) -> bool:
        """从标签移除账号组"""
        try:
            tag = await AccountTag.get_or_none(id=tag_id)
            group = await AccountGroup.get_or_none(id=group_id)
            if not tag or not group:
                return False
                
            await tag.groups.remove(group)
            return True
        except Exception as e:
            logger.error(f"从标签移除账号组失败: {e}")
            raise

    async def get_account_tags_mapping(self) -> Dict[int, List[str]]:
        """获取所有的 账号ID -> 标签名称列表 映射。
        会合并直接关联给账号的标签，以及该账号所在账号组上的标签。
        """
        mapping: Dict[int, set] = {}
        
        try:
            # 获取所有具有 tags 的 accounts
            accounts_with_tags = await PlatformAccount.all().prefetch_related("tags")
            for acc in accounts_with_tags:
                if acc.id not in mapping:
                    mapping[acc.id] = set()
                tags = await acc.tags.all()
                for t in tags:
                    mapping[acc.id].add(t.name)
            
            # 获取所有具有 tags 的 groups
            groups_with_tags = await AccountGroup.all().prefetch_related("tags", "accounts")
            for group in groups_with_tags:
                tags = await group.tags.all()
                group_tag_names = [t.name for t in tags]
                
                if group_tag_names:
                    # 获取该组下的所有账号
                    accs_in_group = await group.accounts.all()
                    for acc in accs_in_group:
                        if acc.id not in mapping:
                            mapping[acc.id] = set()
                        for tn in group_tag_names:
                            mapping[acc.id].add(tn)
                            
            # 转为 list
            result_mapping = {acc_id: list(tags_set) for acc_id, tags_set in mapping.items()}
            return result_mapping
            
        except Exception as e:
            logger.error(f"获取账号标签映射失败: {e}")
            return {}
