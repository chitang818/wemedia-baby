"""
账号组表 ORM 模型
对应数据库表：account_groups
"""

from tortoise import fields
from tortoise.models import Model


class AccountGroup(Model):
    """账号组表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        user: 关联用户（外键）
        group_name: 组名（同一用户下唯一）
        description: 描述（可选）
        created_at: 创建时间（自动填充）
        updated_at: 更新时间（可选）
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="account_groups", on_delete=fields.CASCADE
    )
    group_name = fields.CharField(max_length=100)
    description = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "account_groups"
        # 同一用户下组名唯一
        unique_together = (("user", "group_name"),)

    def __str__(self):
        return f"AccountGroup(id={self.id}, name={self.group_name})"
