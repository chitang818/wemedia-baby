"""
随机文案库相关的 ORM 模型
"""

from tortoise import fields
from tortoise.models import Model


class RandomCopywritingCategory(Model):
    """随机文案库分类表"""

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "random_copywriting_categories"

    def __str__(self):
        return f"RandomCopywritingCategory(id={self.id}, name={self.name})"


class RandomCopywritingItem(Model):
    """随机文案库文案条目表"""

    id = fields.IntField(pk=True)
    # 级联删除：删除分类时，分类下的所有文案也同步删除
    category = fields.ForeignKeyField(
        "models.RandomCopywritingCategory", 
        related_name="items",
        on_delete=fields.CASCADE
    )
    work_id = fields.CharField(max_length=200, null=True)
    short_title = fields.CharField(max_length=500, null=True)
    description = fields.TextField(null=True)
    topics = fields.TextField(null=True)
    content = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "random_copywriting_items"

    def __str__(self):
        return f"RandomCopywritingItem(id={self.id}, category_id={self.category_id})"
