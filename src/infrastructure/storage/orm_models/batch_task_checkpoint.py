"""
批量任务检查点表 ORM 模型
对应数据库表：batch_task_checkpoints
"""

from tortoise import fields
from tortoise.models import Model


class BatchTaskCheckpoint(Model):
    """批量任务检查点表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        task: 关联批量任务（外键，级联删除，唯一）
        completed_indices: 已完成的索引列表（JSON字符串）
        current_index: 当前索引
        checkpoint_data: 检查点数据（JSON字符串，可选）
        created_at: 创建时间（自动填充）
        updated_at: 更新时间（可选）
    """

    id = fields.IntField(pk=True)
    task = fields.OneToOneField(
        "models.BatchTask", related_name="checkpoint", on_delete=fields.CASCADE
    )
    completed_indices = fields.TextField()
    current_index = fields.IntField(default=0)
    checkpoint_data = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "batch_task_checkpoints"

    def __str__(self):
        return f"BatchTaskCheckpoint(id={self.id}, task_id={self.task_id})"
