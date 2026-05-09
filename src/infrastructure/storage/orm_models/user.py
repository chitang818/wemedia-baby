"""
用户表 ORM 模型
对应数据库表：users
"""

from tortoise import fields
from tortoise.models import Model


class User(Model):
    """用户表 ORM 模型

    字段说明：
        id: 用户主键ID（自增）
        username: 用户名（唯一）
        password_hash: 密码哈希值
        email: 邮箱
        role: 角色（默认 'user'）
        trial_count: 试用次数（默认 5）
        created_at: 创建时间（自动填充）
        last_login_at: 最后登录时间（可选）
    """

    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=100, unique=True)
    password_hash = fields.TextField()
    email = fields.CharField(max_length=200)
    role = fields.CharField(max_length=20, default="user")
    trial_count = fields.IntField(default=5)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_login_at = fields.DatetimeField(null=True)

    class Meta:
        table = "users"

    def __str__(self):
        return f"User(id={self.id}, username={self.username})"
