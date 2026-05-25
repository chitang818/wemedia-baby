"""
位置推广配置 ORM 模型
对应数据库表：location_promotion_items
"""

from tortoise import fields
from tortoise.models import Model


class LocationPromotionItem(Model):
    """位置推广配置表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        short_name: 位置简称（唯一，创建任务时选择用）
        douyin_location: 抖音平台搜索词
        kuaishou_location: 快手平台搜索词
        channels_location: 视频号平台搜索词
        xiaohongshu_location: 小红书平台搜索词
        created_at: 创建时间
        updated_at: 更新时间
    """

    id = fields.IntField(primary_key=True)
    short_name = fields.CharField(max_length=500, unique=True)
    douyin_location = fields.TextField(null=True)
    kuaishou_location = fields.TextField(null=True)
    channels_location = fields.TextField(null=True)
    xiaohongshu_location = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "location_promotion_items"

    def __str__(self):
        return f"LocationPromotionItem(id={self.id}, short_name={self.short_name})"
