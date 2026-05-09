"""
环境自检模块（Doctor）
文件路径：src/infrastructure/monitoring/doctor.py
功能：检查运行环境是否满足软件要求，帮助用户快速定位环境问题

检查项：
1. Python 版本检查
2. 系统资源检查（CPU、内存、磁盘空间）
3. 必要依赖检查（FFmpeg、VC++ 运行库等）
4. 网络连通性检查
5. 配置文件完整性检查
"""

import sys
import os
import platform
import shutil
import subprocess
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """检查状态枚举"""
    PASS = "pass"           # 通过
    WARNING = "warning"     # 警告（可继续运行）
    FAIL = "fail"          # 失败（可能影响功能）
    CRITICAL = "critical"   # 严重（无法运行）


@dataclass
class CheckResult:
    """检查结果"""
    name: str               # 检查项名称
    status: CheckStatus     # 检查状态
    message: str            # 结果消息
    suggestion: Optional[str] = None  # 修复建议
    details: Optional[Dict[str, Any]] = None  # 详细信息


class EnvironmentDoctor:
    """环境自检医生 - 检查运行环境是否满足要求"""
    
    # 最低 Python 版本要求
    MIN_PYTHON_VERSION = (3, 10)
    RECOMMENDED_PYTHON_VERSION = (3, 12)
    
    # 最低磁盘空间要求（MB）
    MIN_DISK_SPACE_MB = 500
    RECOMMENDED_DISK_SPACE_MB = 2000
    
    # 最低内存要求（MB）
    MIN_MEMORY_MB = 1024
    RECOMMENDED_MEMORY_MB = 4096
    
    def __init__(self):
        self.results: List[CheckResult] = []
        self.logger = logging.getLogger(__name__)
    
    async def run_all_checks(self) -> List[CheckResult]:
        """运行所有检查
        
        Returns:
            所有检查结果列表
        """
        self.results = []
        
        # 按优先级运行检查
        await self.check_python_version()
        await self.check_system_resources()
        await self.check_required_dependencies()
        await self.check_config_files()
        await self.check_network_connectivity()
        
        # 记录汇总日志
        passed = sum(1 for r in self.results if r.status == CheckStatus.PASS)
        warnings = sum(1 for r in self.results if r.status == CheckStatus.WARNING)
        failed = sum(1 for r in self.results if r.status in [CheckStatus.FAIL, CheckStatus.CRITICAL])
        
        self.logger.info(f"环境自检完成: {passed} 通过, {warnings} 警告, {failed} 失败")
        
        return self.results
    
    async def check_python_version(self) -> CheckResult:
        """检查 Python 版本"""
        version = sys.version_info[:3]
        version_str = f"{version[0]}.{version[1]}.{version[2]}"
        
        if version[:2] < self.MIN_PYTHON_VERSION:
            result = CheckResult(
                name="Python 版本",
                status=CheckStatus.CRITICAL,
                message=f"Python 版本 {version_str} 过低",
                suggestion=f"请升级到 Python {self.MIN_PYTHON_VERSION[0]}.{self.MIN_PYTHON_VERSION[1]} 或更高版本",
                details={"current": version_str, "minimum": f"{self.MIN_PYTHON_VERSION[0]}.{self.MIN_PYTHON_VERSION[1]}"}
            )
        elif version[:2] < self.RECOMMENDED_PYTHON_VERSION:
            result = CheckResult(
                name="Python 版本",
                status=CheckStatus.WARNING,
                message=f"Python 版本 {version_str} 可用，但建议升级",
                suggestion=f"建议升级到 Python {self.RECOMMENDED_PYTHON_VERSION[0]}.{self.RECOMMENDED_PYTHON_VERSION[1]}",
                details={"current": version_str, "recommended": f"{self.RECOMMENDED_PYTHON_VERSION[0]}.{self.RECOMMENDED_PYTHON_VERSION[1]}"}
            )
        else:
            result = CheckResult(
                name="Python 版本",
                status=CheckStatus.PASS,
                message=f"Python {version_str} ✓",
                details={"current": version_str}
            )
        
        self.results.append(result)
        return result
    
    async def check_system_resources(self) -> List[CheckResult]:
        """检查系统资源（CPU、内存、磁盘）"""
        results = []
        
        try:
            import psutil
            
            # 检查内存
            memory = psutil.virtual_memory()
            total_memory_mb = memory.total / (1024 * 1024)
            available_memory_mb = memory.available / (1024 * 1024)
            
            if total_memory_mb < self.MIN_MEMORY_MB:
                mem_result = CheckResult(
                    name="系统内存",
                    status=CheckStatus.WARNING,
                    message=f"内存 {total_memory_mb:.0f}MB 较低",
                    suggestion=f"建议至少 {self.RECOMMENDED_MEMORY_MB}MB 内存",
                    details={"total_mb": total_memory_mb, "available_mb": available_memory_mb}
                )
            else:
                mem_result = CheckResult(
                    name="系统内存",
                    status=CheckStatus.PASS,
                    message=f"内存 {total_memory_mb:.0f}MB ✓",
                    details={"total_mb": total_memory_mb, "available_mb": available_memory_mb}
                )
            
            results.append(mem_result)
            self.results.append(mem_result)
            
            # 检查磁盘空间（当前工作目录所在磁盘）
            disk = psutil.disk_usage(os.getcwd())
            free_disk_mb = disk.free / (1024 * 1024)
            
            if free_disk_mb < self.MIN_DISK_SPACE_MB:
                disk_result = CheckResult(
                    name="磁盘空间",
                    status=CheckStatus.FAIL,
                    message=f"磁盘空间不足 ({free_disk_mb:.0f}MB)",
                    suggestion=f"请清理磁盘，至少需要 {self.MIN_DISK_SPACE_MB}MB 空闲空间",
                    details={"free_mb": free_disk_mb, "minimum_mb": self.MIN_DISK_SPACE_MB}
                )
            elif free_disk_mb < self.RECOMMENDED_DISK_SPACE_MB:
                disk_result = CheckResult(
                    name="磁盘空间",
                    status=CheckStatus.WARNING,
                    message=f"磁盘空间较低 ({free_disk_mb:.0f}MB)",
                    suggestion=f"建议至少 {self.RECOMMENDED_DISK_SPACE_MB}MB 空闲空间",
                    details={"free_mb": free_disk_mb, "recommended_mb": self.RECOMMENDED_DISK_SPACE_MB}
                )
            else:
                disk_result = CheckResult(
                    name="磁盘空间",
                    status=CheckStatus.PASS,
                    message=f"磁盘空间 {free_disk_mb / 1024:.1f}GB ✓",
                    details={"free_mb": free_disk_mb}
                )
            
            results.append(disk_result)
            self.results.append(disk_result)
            
            # 检查 CPU
            cpu_count = psutil.cpu_count()
            cpu_result = CheckResult(
                name="CPU",
                status=CheckStatus.PASS,
                message=f"CPU {cpu_count} 核心 ✓",
                details={"cores": cpu_count}
            )
            results.append(cpu_result)
            self.results.append(cpu_result)
            
        except ImportError:
            result = CheckResult(
                name="系统资源",
                status=CheckStatus.WARNING,
                message="无法检查系统资源（psutil 未安装）",
                suggestion="运行: pip install psutil"
            )
            results.append(result)
            self.results.append(result)
        except Exception as e:
            result = CheckResult(
                name="系统资源",
                status=CheckStatus.WARNING,
                message=f"系统资源检查失败: {e}"
            )
            results.append(result)
            self.results.append(result)
        
        return results
    
    async def check_required_dependencies(self) -> List[CheckResult]:
        """检查必要的外部依赖"""
        results = []
        
        # 检查 FFmpeg
        ffmpeg_result = await self._check_ffmpeg()
        results.append(ffmpeg_result)
        self.results.append(ffmpeg_result)
        
        # 检查 VC++ 运行库（仅 Windows）
        if platform.system() == "Windows":
            vcpp_result = await self._check_vcpp_runtime()
            results.append(vcpp_result)
            self.results.append(vcpp_result)
        
        return results
    
    async def _check_ffmpeg(self) -> CheckResult:
        """检查 FFmpeg 是否可用"""
        try:
            # 尝试运行 ffmpeg -version
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # 提取版本信息
                version_line = result.stdout.split('\n')[0] if result.stdout else "未知版本"
                return CheckResult(
                    name="FFmpeg",
                    status=CheckStatus.PASS,
                    message=f"FFmpeg 已安装 ✓",
                    details={"version": version_line}
                )
            else:
                return CheckResult(
                    name="FFmpeg",
                    status=CheckStatus.FAIL,
                    message="FFmpeg 执行失败",
                    suggestion="请检查 FFmpeg 安装是否正确，下载地址: https://ffmpeg.org/download.html"
                )
                
        except FileNotFoundError:
            return CheckResult(
                name="FFmpeg",
                status=CheckStatus.WARNING,
                message="FFmpeg 未安装或不在 PATH 中",
                suggestion="视频处理功能需要 FFmpeg，下载地址: https://ffmpeg.org/download.html"
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                name="FFmpeg",
                status=CheckStatus.WARNING,
                message="FFmpeg 检测超时",
                suggestion="请手动验证 FFmpeg 是否正常工作"
            )
        except Exception as e:
            return CheckResult(
                name="FFmpeg",
                status=CheckStatus.WARNING,
                message=f"FFmpeg 检测失败: {e}"
            )
    
    async def _check_vcpp_runtime(self) -> CheckResult:
        """检查 VC++ 运行库是否安装（仅 Windows）"""
        try:
            import winreg
            
            # 检查常见的 VC++ 运行库注册表位置
            vcpp_keys = [
                # VC++ 2015-2022 x64
                r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
                # VC++ 2015-2022 x86
                r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
                # WoW6432Node
                r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
            ]
            
            for key_path in vcpp_keys:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    version, _ = winreg.QueryValueEx(key, "Version")
                    winreg.CloseKey(key)
                    
                    return CheckResult(
                        name="VC++ 运行库",
                        status=CheckStatus.PASS,
                        message=f"VC++ 运行库已安装 ✓",
                        details={"version": version}
                    )
                except WindowsError:
                    continue
            
            # 未找到注册表项，但可能通过其他方式安装
            return CheckResult(
                name="VC++ 运行库",
                status=CheckStatus.WARNING,
                message="无法确认 VC++ 运行库状态",
                suggestion="如遇 DLL 缺失错误，请安装 VC++ 2015-2022 运行库: https://aka.ms/vs/17/release/vc_redist.x64.exe"
            )
            
        except ImportError:
            # 非 Windows 系统
            return CheckResult(
                name="VC++ 运行库",
                status=CheckStatus.PASS,
                message="非 Windows 系统，跳过检查"
            )
        except Exception as e:
            return CheckResult(
                name="VC++ 运行库",
                status=CheckStatus.WARNING,
                message=f"VC++ 运行库检测失败: {e}"
            )
    
    async def check_config_files(self) -> List[CheckResult]:
        """检查用户配置目录与内置资源是否可用（不依赖当前工作目录）。"""
        from src.infrastructure.common.bundled_config import bundled_file_path
        from src.infrastructure.common.path_manager import PathManager

        results: List[CheckResult] = []

        # 用户数据目录（app_config.json 由 ConfigCenter 首次运行时创建，缺失非失败）
        cfg_dir = PathManager.get_config_dir()
        try:
            cfg_dir.mkdir(parents=True, exist_ok=True)
            probe = cfg_dir / ".write_probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            r = CheckResult(
                name="用户配置目录",
                status=CheckStatus.PASS,
                message="用户配置目录可写 ✓",
                details={"path": str(cfg_dir.resolve())},
            )
        except OSError as e:
            r = CheckResult(
                name="用户配置目录",
                status=CheckStatus.FAIL,
                message="用户配置目录不可用",
                suggestion="请检查本机磁盘权限或更换用户数据目录权限",
                details={"path": str(cfg_dir.resolve()), "error": str(e)},
            )
        results.append(r)
        self.results.append(r)

        app_cfg = cfg_dir / "app_config.json"
        if app_cfg.is_file():
            r = CheckResult(
                name="用户应用配置",
                status=CheckStatus.PASS,
                message="app_config.json 已存在 ✓",
                details={"path": str(app_cfg.resolve())},
            )
        else:
            r = CheckResult(
                name="用户应用配置",
                status=CheckStatus.WARNING,
                message="尚未生成 app_config.json",
                suggestion="首次运行保存设置后会自动创建，属正常情况",
                details={"path": str(app_cfg.resolve())},
            )
        results.append(r)
        self.results.append(r)

        # 内置平台规则（安装包完整性）
        bundled_platform = bundled_file_path("config/platforms/douyin.json")
        if bundled_platform.is_file():
            r = CheckResult(
                name="内置平台配置",
                status=CheckStatus.PASS,
                message="内置平台配置完整 ✓",
                details={"path": str(bundled_platform.resolve())},
            )
        else:
            r = CheckResult(
                name="内置平台配置",
                status=CheckStatus.FAIL,
                message="内置平台配置缺失（安装可能不完整）",
                suggestion="请重新安装应用或检查安装目录下 config/platforms 是否完整",
                details={"path": str(bundled_platform.resolve())},
            )
        results.append(r)
        self.results.append(r)

        manifest = bundled_file_path("config/selectors_manifest.json")
        if manifest.is_file():
            r = CheckResult(
                name="选择器清单",
                status=CheckStatus.PASS,
                message="选择器清单 ✓",
                details={"path": str(manifest.resolve())},
            )
        else:
            r = CheckResult(
                name="选择器清单",
                status=CheckStatus.WARNING,
                message="未找到 config/selectors_manifest.json",
                suggestion="部分功能可能依赖该清单；若刚升级版本可尝试重装",
                details={"path": str(manifest.resolve())},
            )
        results.append(r)
        self.results.append(r)

        return results
    
    async def check_network_connectivity(self) -> CheckResult:
        """检查网络连通性"""
        try:
            import aiohttp
            
            test_urls = [
                ("https://www.baidu.com", "百度"),
                ("https://creator.douyin.com", "抖音创作者中心"),
            ]
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                for url, name in test_urls:
                    try:
                        async with session.head(url) as response:
                            if response.status < 400:
                                result = CheckResult(
                                    name="网络连通性",
                                    status=CheckStatus.PASS,
                                    message=f"网络连接正常 ✓",
                                    details={"tested_url": url, "tested_name": name}
                                )
                                self.results.append(result)
                                return result
                    except Exception:
                        continue
            
            # 所有 URL 都无法访问
            result = CheckResult(
                name="网络连通性",
                status=CheckStatus.FAIL,
                message="无法连接网络",
                suggestion="请检查网络连接，确保可以访问互联网"
            )
            
        except ImportError:
            result = CheckResult(
                name="网络连通性",
                status=CheckStatus.WARNING,
                message="无法检查网络（aiohttp 未安装）",
                suggestion="运行: pip install aiohttp"
            )
        except Exception as e:
            result = CheckResult(
                name="网络连通性",
                status=CheckStatus.WARNING,
                message=f"网络检查失败: {e}"
            )
        
        self.results.append(result)
        return result
    
    def get_summary(self) -> Dict[str, Any]:
        """获取检查结果汇总"""
        return {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.status == CheckStatus.PASS),
            "warnings": sum(1 for r in self.results if r.status == CheckStatus.WARNING),
            "failed": sum(1 for r in self.results if r.status == CheckStatus.FAIL),
            "critical": sum(1 for r in self.results if r.status == CheckStatus.CRITICAL),
            "can_run": not any(r.status == CheckStatus.CRITICAL for r in self.results),
            "results": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "suggestion": r.suggestion,
                    "details": r.details
                }
                for r in self.results
            ]
        }
    
    def print_report(self):
        """打印检查报告到控制台"""
        print("\n" + "=" * 50)
        print("环境自检报告")
        print("=" * 50)
        
        for result in self.results:
            status_icon = {
                CheckStatus.PASS: "✓",
                CheckStatus.WARNING: "⚠",
                CheckStatus.FAIL: "✗",
                CheckStatus.CRITICAL: "☠"
            }.get(result.status, "?")
            
            print(f"\n[{status_icon}] {result.name}")
            print(f"    {result.message}")
            if result.suggestion:
                print(f"    建议: {result.suggestion}")
        
        summary = self.get_summary()
        print("\n" + "-" * 50)
        print(f"汇总: {summary['passed']} 通过, {summary['warnings']} 警告, {summary['failed']} 失败, {summary['critical']} 严重")
        print(f"系统状态: {'可以运行' if summary['can_run'] else '无法运行'}")
        print("=" * 50 + "\n")


# 便捷函数
async def run_environment_check() -> Dict[str, Any]:
    """运行环境检查并返回结果
    
    Returns:
        检查结果汇总字典
    """
    doctor = EnvironmentDoctor()
    await doctor.run_all_checks()
    return doctor.get_summary()


# 命令行入口
if __name__ == "__main__":
    async def main():
        doctor = EnvironmentDoctor()
        await doctor.run_all_checks()
        doctor.print_report()
    
    asyncio.run(main())
