"""
性能指标采集模块
文件路径：src/core/monitoring/metrics.py
功能：采集性能指标，监控系统资源使用
"""

import time
import psutil
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)


class MetricsCollector:
    """性能指标采集器
    
    采集关键操作的耗时、系统资源使用等指标。
    """
    
    def __init__(self, max_history: int = 1000):
        """初始化性能指标采集器
        
        Args:
            max_history: 最大历史记录数
        """
        self.max_history = max_history
        self.operation_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.operation_counts: Dict[str, int] = defaultdict(int)
        self.operation_errors: Dict[str, int] = defaultdict(int)
        self.logger = logging.getLogger(__name__)
    
    def record_operation(
        self,
        operation_name: str,
        duration: float,
        success: bool = True
    ) -> None:
        """记录操作耗时
        
        Args:
            operation_name: 操作名称
            duration: 耗时（秒）
            success: 是否成功
        """
        self.operation_times[operation_name].append(duration)
        self.operation_counts[operation_name] += 1
        
        if not success:
            self.operation_errors[operation_name] += 1
    
    def get_operation_stats(self, operation_name: str) -> Dict[str, Any]:
        """获取操作统计信息
        
        Args:
            operation_name: 操作名称
        
        Returns:
            统计信息字典（包含平均耗时、P95耗时、成功率等）
        """
        times = list(self.operation_times[operation_name])
        if not times:
            return {
                'count': 0,
                'avg_duration': 0,
                'p95_duration': 0,
                'min_duration': 0,
                'max_duration': 0,
                'success_rate': 0,
                'error_count': 0
            }
        
        sorted_times = sorted(times)
        count = len(times)
        p95_index = int(count * 0.95)
        
        total_count = self.operation_counts[operation_name]
        error_count = self.operation_errors[operation_name]
        success_count = total_count - error_count
        
        return {
            'count': total_count,
            'avg_duration': sum(times) / count,
            'p95_duration': sorted_times[p95_index] if p95_index < count else sorted_times[-1],
            'min_duration': min(times),
            'max_duration': max(times),
            'success_rate': success_count / total_count if total_count > 0 else 0,
            'error_count': error_count
        }
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统资源指标
        
        Returns:
            系统资源指标字典（CPU、内存、磁盘使用率）
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_mb': memory.used / (1024 * 1024),
                'memory_total_mb': memory.total / (1024 * 1024),
                'disk_percent': disk.percent,
                'disk_used_gb': disk.used / (1024 * 1024 * 1024),
                'disk_total_gb': disk.total / (1024 * 1024 * 1024),
            }
        except Exception as e:
            self.logger.error(f"获取系统指标失败: {e}", exc_info=True)
            return {}
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标
        
        Returns:
            包含所有指标的字典
        """
        operation_stats = {}
        for operation_name in self.operation_times.keys():
            operation_stats[operation_name] = self.get_operation_stats(operation_name)
        
        return {
            'operations': operation_stats,
            'system': self.get_system_metrics()
        }


class OperationTimer:
    """操作计时器（上下文管理器）
    
    用于自动记录操作耗时。
    """
    
    def __init__(self, metrics_collector: MetricsCollector, operation_name: str):
        """初始化操作计时器
        
        Args:
            metrics_collector: 指标采集器
            operation_name: 操作名称
        """
        self.metrics_collector = metrics_collector
        self.operation_name = operation_name
        self.start_time: Optional[float] = None
        self.success = True
    
    def __enter__(self):
        """进入上下文"""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if self.start_time is not None:
            duration = time.time() - self.start_time
            self.success = exc_type is None
            self.metrics_collector.record_operation(
                self.operation_name,
                duration,
                self.success
            )

