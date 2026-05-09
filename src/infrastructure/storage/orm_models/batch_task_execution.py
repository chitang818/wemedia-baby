"""
批量任务执行记录表 ORM 模型
对应数据库表：batch_task_executions
"""

from tortoise import fields
from tortoise.models import Model


class BatchTaskExecution(Model):
    """批量任务执行记录表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        task: 关联批量任务（外键，级联删除）
        execution_index: 执行序号
        file_path: 文件路径
        title: 标题（可选）
        description: 描述（可选）
        status: 执行状态
        error_message: 错误信息（可选）
        retry_count: 重试次数
        publish_url: 发布链接（可选）
        started_at: 开始时间（可选）
        completed_at: 完成时间（可选）
    """

    id = fields.IntField(pk=True)
    task = fields.ForeignKeyField(
        "models.BatchTask", related_name="executions", on_delete=fields.CASCADE
    )
    execution_index = fields.IntField()
    file_path = fields.TextField()
    title = fields.TextField(null=True)
    description = fields.TextField(null=True)
    status = fields.CharField(max_length=20)
    error_message = fields.TextField(null=True)
    retry_count = fields.IntField(default=0)
    publish_url = fields.TextField(null=True)
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)

    class Meta:
        table = "batch_task_executions"

    def __str__(self):
        return f"BatchTaskExecution(id={self.id}, index={self.execution_index}, status={self.status})"
