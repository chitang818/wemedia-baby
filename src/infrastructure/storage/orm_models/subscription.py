"""
订阅表 ORM 模型
对应数据库表：subscriptions
"""

from tortoise import fields
from tortoise.models import Model


class Subscription(Model):
    """订阅表 ORM 模型

    字段说明：
        id: 订阅主键ID（自增）
        user: 关联用户（外键）
        plan_type: 套餐类型（trial/basic/premium）
        price: 价格
        start_date: 开始日期
        end_date: 结束日期
        auto_renew: 是否自动续费（0/1）
        status: 订阅状态（active/expired/cancelled）
        payment_method: 支付方式（可选）
        order_id: 订单号（唯一、可选）
        created_at: 创建时间（自动填充）
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="subscriptions", on_delete=fields.CASCADE
    )
    plan_type = fields.CharField(max_length=50)
    price = fields.FloatField()
    start_date = fields.DatetimeField()
    end_date = fields.DatetimeField()
    auto_renew = fields.BooleanField(default=False)
    status = fields.CharField(max_length=20, default="active")
    payment_method = fields.CharField(max_length=50, null=True)
    order_id = fields.CharField(max_length=100, unique=True, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "subscriptions"

    def __str__(self):
        return f"Subscription(id={self.id}, plan={self.plan_type}, status={self.status})"
