"""
文案库表 ORM 模型
对应数据库表：copywriting_items
"""

from tortoise import fields
from tortoise.models import Model


class CopywritingItem(Model):
    """文案库表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        work_id: 作品编号（唯一，用于 Excel 导入时覆盖匹配）
        short_title: 作品标题
        description: 作品简介
        topics: 话题（以字符串形式存储，可为逗号分隔或原样）
        content: 文案内容
        category: 类别标签（通常为 Excel 中的 Sheet Name）
        created_at: 创建时间
        updated_at: 更新时间
    """

    id = fields.IntField(primary_key=True)
    work_id = fields.CharField(max_length=200, unique=True)
    short_title = fields.CharField(max_length=500, null=True)
    description = fields.TextField(null=True)
    topics = fields.TextField(null=True)
    category = fields.CharField(max_length=100, null=True, default="全部")
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:  # type: ignore
        table = "copywriting_items"

    def __str__(self):
        return f"CopywritingItem(id={self.id}, work_id={self.work_id})"
