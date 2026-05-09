"""
登录日志表 ORM 模型
对应数据库表：login_logs
"""

from tortoise import fields
from tortoise.models import Model


class LoginLog(Model):
    """登录日志表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        user: 关联用户（外键）
        login_time: 登录时间（自动填充）
        device_info: 设备信息（可选）
        ip_address: IP 地址（可选）
        login_status: 登录状态（可选）
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="login_logs", on_delete=fields.CASCADE
    )
    login_time = fields.DatetimeField(auto_now_add=True)
    device_info = fields.TextField(null=True)
    ip_address = fields.CharField(max_length=50, null=True)
    login_status = fields.CharField(max_length=20, null=True)

    class Meta:
        table = "login_logs"

    def __str__(self):
        return f"LoginLog(id={self.id}, user_id={self.user_id})"
