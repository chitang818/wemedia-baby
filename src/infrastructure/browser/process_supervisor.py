"""
浏览器进程守护
文件路径：src/infrastructure/browser/process_supervisor.py
功能：跟踪并清理由本软件启动的浏览器进程，防止僵尸进程
"""

import os
import logging
import atexit
from typing import Set

logger = logging.getLogger(__name__)


class ProcessSupervisor:
    """浏览器进程守护 (单例)
    
    职责：
    1. 注册由本软件启动的浏览器进程 PID
    2. 在软件退出时强制清理所有残留进程
    """
    
    _instance = None
    _child_pids: Set[int] = set()
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def initialize(cls):
        """初始化并注册 atexit 钩子"""
        if cls._initialized:
            return
        
        atexit.register(cls.cleanup)
        cls._initialized = True
        logger.info("ProcessSupervisor 已初始化 (atexit 已注册)")
    
    @classmethod
    def register(cls, pid: int):
        """注册子进程 PID
        
        Args:
            pid: 进程 ID
        """
        cls._child_pids.add(pid)
        logger.debug(f"注册浏览器进程: PID={pid}")
    
    @classmethod
    def unregister(cls, pid: int):
        """注销子进程 PID
        
        Args:
            pid: 进程 ID
        """
        cls._child_pids.discard(pid)
        logger.debug(f"注销浏览器进程: PID={pid}")
    
    @classmethod
    def cleanup(cls):
        """清理所有残留进程"""
        if not cls._child_pids:
            logger.debug("无需清理浏览器进程")
            return
        
        logger.info(f"正在清理 {len(cls._child_pids)} 个残留浏览器进程...")
        
        try:
            import psutil
            
            for pid in list(cls._child_pids):
                try:
                    proc = psutil.Process(pid)
                    proc.terminate()
                    logger.debug(f"已终止进程: PID={pid}")
                except psutil.NoSuchProcess:
                    logger.debug(f"进程已不存在: PID={pid}")
                except Exception as e:
                    logger.warning(f"终止进程失败: PID={pid}, error={e}")
            
            cls._child_pids.clear()
            logger.info("浏览器进程清理完成")
            
        except ImportError:
            logger.warning("psutil 未安装，无法清理进程。建议安装: pip install psutil")
        except Exception as e:
            logger.error(f"进程清理失败: {e}")
    
    @classmethod
    def force_kill_all_chrome(cls):
        """强制杀死所有 Chrome/Chromium 进程 (危险操作，仅用于紧急情况)"""
        try:
            import psutil
            
            killed_count = 0
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    name = proc.info['name'].lower()
                    if 'chrome' in name or 'chromium' in name:
                        proc.kill()
                        killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            logger.warning(f"强制终止了 {killed_count} 个 Chrome 相关进程")
            
        except ImportError:
            logger.error("psutil 未安装")
        except Exception as e:
            logger.error(f"强制终止失败: {e}")
