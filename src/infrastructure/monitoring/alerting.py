"""
异常报警模块
文件路径：src/core/monitoring/alerting.py
功能：提供异常报警功能，监控系统状态并发送告警
"""

from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """告警信息"""
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None


class AlertManager:
    """异常报警管理器
    
    监控系统状态，根据规则发送告警。
    """
    
    def __init__(self):
        """初始化异常报警管理器"""
        self.alert_history: List[Alert] = []
        self.alert_callbacks: List[Callable[[Alert], None]] = []
        self.alert_rules: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
        
        # 初始化默认告警规则
        self._init_default_rules()
    
    def _init_default_rules(self) -> None:
        """初始化默认告警规则"""
        self.alert_rules = {
            'cpu_high': {
                'condition': lambda metrics: metrics.get('cpu_percent', 0) > 80,
                'level': AlertLevel.WARNING,
                'title': 'CPU使用率过高'
            },
            'memory_high': {
                'condition': lambda metrics: metrics.get('memory_percent', 0) > 90,
                'level': AlertLevel.ERROR,
                'title': '内存使用率过高'
            },
            'publish_failure_rate': {
                'condition': lambda stats: stats.get('success_rate', 1.0) < 0.7,
                'level': AlertLevel.ERROR,
                'title': '发布失败率过高'
            }
        }
    
    def add_alert_callback(self, callback: Callable[[Alert], None]) -> None:
        """添加告警回调
        
        Args:
            callback: 告警回调函数
        """
        self.alert_callbacks.append(callback)
    
    async def check_alerts(self, metrics: Dict[str, Any]) -> List[Alert]:
        """检查告警（异步）
        
        Args:
            metrics: 系统指标字典
        
        Returns:
            触发的告警列表
        """
        alerts = []
        
        # 检查系统资源告警
        system_metrics = metrics.get('system', {})
        for rule_name, rule in self.alert_rules.items():
            if rule_name.startswith('cpu_') or rule_name.startswith('memory_'):
                if rule['condition'](system_metrics):
                    alert = Alert(
                        level=rule['level'],
                        title=rule['title'],
                        message=f"{rule_name}: {system_metrics}",
                        timestamp=datetime.now(),
                        details=system_metrics
                    )
                    alerts.append(alert)
                    await self._send_alert(alert)
        
        # 检查操作统计告警
        operations = metrics.get('operations', {})
        for operation_name, stats in operations.items():
            if 'publish' in operation_name.lower():
                if self.alert_rules.get('publish_failure_rate', {}).get('condition')(stats):
                    alert = Alert(
                        level=AlertLevel.ERROR,
                        title='发布失败率过高',
                        message=f"{operation_name} 失败率: {1 - stats.get('success_rate', 0):.2%}",
                        timestamp=datetime.now(),
                        details=stats
                    )
                    alerts.append(alert)
                    await self._send_alert(alert)
        
        return alerts
    
    async def _send_alert(self, alert: Alert) -> None:
        """发送告警（异步）
        
        Args:
            alert: 告警信息
        """
        # 记录告警历史
        self.alert_history.append(alert)
        # 只保留最近1000条告警
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]
        
        # 调用所有回调
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"执行告警回调失败: {e}", exc_info=True)
        
        # 记录日志
        log_level = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.ERROR: logging.ERROR,
            AlertLevel.CRITICAL: logging.CRITICAL,
        }.get(alert.level, logging.INFO)
        
        self.logger.log(
            log_level,
            f"告警: {alert.title} - {alert.message}"
        )
    
    def get_alert_history(
        self,
        level: Optional[AlertLevel] = None,
        limit: int = 100
    ) -> List[Alert]:
        """获取告警历史
        
        Args:
            level: 告警级别（可选，过滤）
            limit: 返回数量限制
        
        Returns:
            告警列表
        """
        alerts = self.alert_history
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        return alerts[-limit:]

