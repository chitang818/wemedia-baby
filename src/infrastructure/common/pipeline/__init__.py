"""
发布管道模块
提供发布流程的管道-过滤器模式实现
"""

from .publish_pipeline import PublishPipeline, PublishRequest, PublishResponse, PublishContext
from .base_filter import BaseFilter, IPublishFilter, PipelineResult

# 向后兼容：旧代码 from ...pipeline import PublishResult 仍可用
PublishResult = PipelineResult

__all__ = [
    'PublishPipeline',
    'PublishRequest',
    'PublishResponse',
    'PipelineResult',
    'PublishResult',
    'PublishContext',
    'BaseFilter',
    'IPublishFilter',
]

