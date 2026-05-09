"""
批量任务表 ORM 模型
对应数据库表：batch_tasks
"""

from tortoise import fields
from tortoise.models import Model


class BatchTask(Model):
    """批量任务表 ORM 模型

    字段说明：
        id: 主键ID（自增）
        user: 关联用户（外键）
        task_name: 任务名称
        task_description: 任务描述（可选）
        platform_username: 平台账号用户名
        platform: 平台名称
        task_type: 任务类型
        script_config: 脚本配置（JSON字符串）
        video_count: 视频数量
        status: 任务状态（pending/running/completed/failed/cancelled）
        completed_count: 已完成数量
        failed_count: 失败数量
        start_time: 开始时间（可选）
        end_time: 结束时间（可选）
        priority: 优先级（默认 0）
        retry_count: 重试次数（默认 3）
        delay_seconds: 延迟秒数（默认 5）
        max_concurrent: 最大并发数（默认 1）
        created_at: 创建时间（自动填充）
        updated_at: 更新时间（可选）
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="batch_tasks", on_delete=fields.CASCADE
    )
    task_name = fields.CharField(max_length=200)
    task_description = fields.TextField(null=True)
    platform_username = fields.CharField(max_length=200)
    platform = fields.CharField(max_length=50)
    task_type = fields.CharField(max_length=50)
    script_config = fields.TextField()
    video_count = fields.IntField()
    status = fields.CharField(max_length=20)
    completed_count = fields.IntField(default=0)
    failed_count = fields.IntField(default=0)
    start_time = fields.DatetimeField(null=True)
    end_time = fields.DatetimeField(null=True)
    priority = fields.IntField(default=0)
    retry_count = fields.IntField(default=3)
    delay_seconds = fields.IntField(default=5)
    max_concurrent = fields.IntField(default=1)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "batch_tasks"

    def __str__(self):
        return f"BatchTask(id={self.id}, name={self.task_name}, status={self.status})"
