"""
购物车推广商品配置 ORM 模型
对应数据库表：cart_promotion_items
"""

from tortoise import fields
from tortoise.models import Model


class CartPromotionItem(Model):
    """购物车推广商品配置表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        short_name: 商品简称（唯一，用于 Excel 导入时覆盖匹配）
        short_title: 商品短标题（最多 10 字；列表/预览展示；发布仍按平台取链接）
        douyin_link: 抖音链接
        kuaishou_product_name: 快手商品名称
        channels_id_or_link: 视频号 ID 或链接
        xiaohongshu_link: 小红书链接
        created_at: 创建时间
        updated_at: 更新时间
    """

    id = fields.IntField(pk=True)
    short_name = fields.CharField(max_length=500, unique=True)
    short_title = fields.TextField(null=True)
    douyin_link = fields.TextField(null=True)
    kuaishou_product_name = fields.TextField(null=True)
    channels_id_or_link = fields.TextField(null=True)
    xiaohongshu_link = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "cart_promotion_items"

    def __str__(self):
        return f"CartPromotionItem(id={self.id}, short_name={self.short_name})"
