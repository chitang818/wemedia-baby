"""
平台账号表 ORM 模型
对应数据库表：platform_accounts
"""

from tortoise import fields
from tortoise.models import Model


class PlatformAccount(Model):
    """平台账号表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        user: 关联用户（外键）
        platform: 平台名称（如 douyin/kuaishou/xiaohongshu）
        cookie_path: Cookie 文件路径
        platform_username: 平台昵称（如"我真的太难了"）
        login_status: 登录状态（online/offline）
        last_login_at: 最后登录时间（可选）
        profile_folder_name: 浏览器配置文件夹名（UUID）
        group: 关联账号组（外键、可选）
        created_at: 创建时间（自动填充）
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="platform_accounts", on_delete=fields.CASCADE
    )
    platform = fields.CharField(max_length=50)
    cookie_path = fields.CharField(max_length=500, default="")
    platform_username = fields.CharField(max_length=200, default="")
    login_status = fields.CharField(max_length=20, default="offline")
    last_login_at = fields.DatetimeField(null=True)
    profile_folder_name = fields.CharField(max_length=200, null=True)
    group = fields.ForeignKeyField(
        "models.AccountGroup", related_name="accounts", on_delete=fields.SET_NULL, null=True
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "platform_accounts"

    def __str__(self):
        return f"PlatformAccount(id={self.id}, platform={self.platform}, username={self.platform_username})"
