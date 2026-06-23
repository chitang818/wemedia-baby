"""
互动与私信 ORM 模型
文件路径：src/infrastructure/storage/orm_models/interaction.py
"""

from tortoise import fields, models

class MessageSessionModel(models.Model):
    """
    私信会话持久化模型
    对应与某个用户的聊天窗口
    """
    id = fields.IntField(pk=True)
    platform = fields.CharField(max_length=50, description="所属平台，如 douyin")
    account_id = fields.CharField(max_length=100, description="本方账号ID", index=True)
    session_id = fields.CharField(max_length=100, description="会话唯一标识(对应目标ID)", index=True)
    
    target_name = fields.CharField(max_length=100, description="目标昵称")
    target_avatar = fields.CharField(max_length=500, description="目标头像URL", null=True)
    
    last_message = fields.TextField(description="最后一条消息概览", null=True)
    unread_count = fields.IntField(default=0, description="未读数量")
    update_time = fields.DatetimeField(auto_now=True, description="最后活跃时间")
    
    class Meta:  # type: ignore
        table = "interaction_message_sessions"
        unique_together = (("platform", "account_id", "session_id"),)

class ChatMessageModel(models.Model):
    """
    单条聊天记录持久化模型
    """
    id = fields.IntField(pk=True)
    session = fields.ForeignKeyField('models.MessageSessionModel', related_name='messages', on_delete=fields.CASCADE)
    
    message_id = fields.CharField(max_length=100, unique=True, description="平台端消息唯一标识")
    content = fields.TextField(description="消息内容(可能为JSON文本)")
    msg_type = fields.CharField(max_length=50, default="text", description="消息类型: text, image, video等")
    
    sender_id = fields.CharField(max_length=100, description="发送者ID")
    sender_name = fields.CharField(max_length=100, description="发送者昵称")
    is_self = fields.BooleanField(default=False, description="是否是本账号发出的")
    
    create_time = fields.DatetimeField(description="消息创建时间(平台侧时间)")
    
    class Meta:  # type: ignore
        table = "interaction_chat_messages"
        ordering = ["-create_time"]
