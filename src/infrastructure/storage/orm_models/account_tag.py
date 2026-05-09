"""
账号标签表 ORM 模型
"""

from tortoise import fields
from tortoise.models import Model


class AccountTag(Model):
    """账号标签表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        user: 关联用户（外键）
        name: 标签名称（如"农业"）
        created_at: 创建时间
        
    关联说明:
        accounts: 关联的平台账号 (多对多)
        groups: 关联的账号组 (多对多)
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="account_tags", on_delete=fields.CASCADE
    )
    name = fields.CharField(max_length=100)
    # 标签类型：account=账号标签，group=账号组标签
    # 说明：旧数据没有该列时，会在启动时自动补列并默认填充为 account（兼容历史行为）
    tag_type = fields.CharField(max_length=20, default="account")
    
    # 标签和平台账号的多对多关系
    accounts = fields.ManyToManyField(
        "models.PlatformAccount",
        related_name="tags",
        through="account_tag_account_mapping"
    )
    
    # 标签和账号组的多对多关系
    groups = fields.ManyToManyField(
        "models.AccountGroup",
        related_name="tags",
        through="account_tag_group_mapping"
    )
    
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "account_tags"

    def __str__(self):
        return f"AccountTag(id={self.id}, name={self.name})"
