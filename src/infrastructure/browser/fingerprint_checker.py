"""
指纹一致性检查器
文件路径:src/infrastructure/browser/fingerprint_checker.py
功能:检查并修复指纹配置的一致性问题
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class FingerprintConsistencyChecker:
    """指纹一致性检查器
    
    确保各指纹参数之间的一致性,避免被检测为伪造指纹
    """
    
    def check_and_fix(self, fingerprint: Dict[str, Any]) -> Dict[str, Any]:
        """检查并修复指纹配置的一致性问题
        
        Args:
            fingerprint: 指纹配置字典
            
        Returns:
            修复后的指纹配置
        """
        logger.debug("开始指纹一致性检查...")

        # 0. WebGL 成对补全，且 vendor 以 renderer 为准（修复历史错误配置）
        from .hardware_profiles import complete_webgl_fields

        complete_webgl_fields(fingerprint)

        # 1. 检查屏幕参数一致性
        self._check_screen_consistency(fingerprint)

        # 2. 检查硬件参数一致性（含显卡档次与 CPU/内存）
        self._check_hardware_consistency(fingerprint)

        self._ensure_cpu_model(fingerprint)
        
        # 3. 检查UA与Platform一致性
        self._check_ua_platform_consistency(fingerprint)
        
        # 4. 检查时区与语言一致性
        self._check_locale_timezone_consistency(fingerprint)

        # 5. 检查 UA-CH 与 UA/Platform 一致性
        self._check_uach_consistency(fingerprint)
        
        logger.debug("指纹一致性检查完成")
        return fingerprint
    
    def _check_screen_consistency(self, fingerprint: Dict[str, Any]) -> None:
        """检查屏幕参数一致性"""
        width = fingerprint.get('screen_width', 1920)
        height = fingerprint.get('screen_height', 1080)
        
        # 检查分辨率是否合理
        if width < 800 or height < 600:
            logger.warning(f"屏幕分辨率过小: {width}x{height}, 调整为1920x1080")
            fingerprint['screen_width'] = 1920
            fingerprint['screen_height'] = 1080
            width, height = 1920, 1080
        
        # 检查可用宽度
        avail_width = fingerprint.get('screen_avail_width', width)
        if avail_width > width:
            logger.warning(f"可用宽度({avail_width})大于屏幕宽度({width}), 修正")
            fingerprint['screen_avail_width'] = width
        
        # 检查可用高度 (应该小于屏幕高度,减去任务栏)
        avail_height = fingerprint.get('screen_avail_height', height - 40)
        if avail_height >= height:
            logger.warning(f"可用高度({avail_height})不小于屏幕高度({height}), 修正")
            fingerprint['screen_avail_height'] = height - 40
        
        # 检查颜色深度
        color_depth = fingerprint.get('screen_color_depth', 24)
        pixel_depth = fingerprint.get('screen_pixel_depth', 24)
        if color_depth != pixel_depth:
            logger.warning(f"颜色深度({color_depth})与像素深度({pixel_depth})不一致, 统一为24")
            fingerprint['screen_color_depth'] = 24
            fingerprint['screen_pixel_depth'] = 24
    
    def _check_hardware_consistency(self, fingerprint: Dict[str, Any]) -> None:
        """检查硬件参数一致性"""
        cores = fingerprint.get('hardware_concurrency', 4)
        memory = fingerprint.get('device_memory', 8)
        
        # 高核心数应该配高内存
        if cores >= 12 and memory < 8:
            logger.warning(f"CPU核心数({cores})较高但内存({memory}GB)较低, 调整内存为16GB")
            fingerprint['device_memory'] = 16
        
        # 低核心数不应该有超高内存
        if cores <= 4 and memory > 16:
            logger.warning(f"CPU核心数({cores})较低但内存({memory}GB)过高, 调整内存为8GB")
            fingerprint['device_memory'] = 8
        
        # 中等核心数配中等内存
        if 4 < cores < 12:
            if memory < 4:
                logger.warning(f"CPU核心数({cores})中等但内存({memory}GB)过低, 调整为8GB")
                fingerprint['device_memory'] = 8
            elif memory > 32:
                logger.warning(f"内存({memory}GB)过高, 调整为16GB")
                fingerprint['device_memory'] = 16

        # 与显卡档次相关的轻量约束（明显不合理时修正）
        from .hardware_profiles import infer_gpu_tier

        renderer = str(fingerprint.get("webgl_renderer") or "")
        gtier = infer_gpu_tier(renderer)
        memory = fingerprint.get("device_memory", 8)
        cores = fingerprint.get("hardware_concurrency", 4)

        if gtier == "high" and memory < 8:
            logger.warning(
                "高端显卡指纹但内存仅 %sGB，调整为 16GB 以符合常见整机配置",
                memory,
            )
            fingerprint["device_memory"] = 16
            memory = 16

        if gtier == "high" and cores < 8:
            logger.warning(
                "高端显卡指纹但 CPU 逻辑核心仅 %s，调整为 8 以符合常见整机配置",
                cores,
            )
            fingerprint["hardware_concurrency"] = 8
            cores = 8

        if gtier == "integrated" and memory > 24:
            logger.warning(
                "集显档位指纹但内存为 %sGB，调整为 16GB 以更符合常见办公机",
                memory,
            )
            fingerprint["device_memory"] = 16

        if gtier == "mid" and memory < 8:
            logger.warning(
                "中端独显指纹但内存仅 %sGB，调整为 8GB",
                memory,
            )
            fingerprint["device_memory"] = 8

    def _ensure_cpu_model(self, fingerprint: Dict[str, Any]) -> None:
        """从整机档案选取真实 CPU 型号；占位文案或与核心/显卡不一致时重算。"""
        from .hardware_profiles import (
            cpu_model_matches_current_hardware,
            is_placeholder_cpu_model,
            resolve_cpu_model_for_fingerprint,
        )

        cores = fingerprint.get("hardware_concurrency", 4)
        mem = fingerprint.get("device_memory", 8)
        renderer = str(fingerprint.get("webgl_renderer") or "")
        current = fingerprint.get("cpu_model")

        if (
            current
            and not is_placeholder_cpu_model(current)
            and cpu_model_matches_current_hardware(current, cores, renderer)
        ):
            return

        fingerprint["cpu_model"] = resolve_cpu_model_for_fingerprint(
            cores, mem, renderer
        )
        logger.debug("已写入 cpu_model（档案）: %s", fingerprint["cpu_model"])

    def _check_ua_platform_consistency(self, fingerprint: Dict[str, Any]) -> None:
        """检查User-Agent与Platform一致性"""
        ua = fingerprint.get('user_agent') or ''
        platform = fingerprint.get('platform', 'Win32')
        
        # 根据UA确定应该的platform
        expected_platform = None
        if 'Windows' in ua:
            expected_platform = 'Win32'
        elif 'Mac' in ua or 'Macintosh' in ua:
            expected_platform = 'MacIntel'
        elif 'Linux' in ua and 'Android' not in ua:
            expected_platform = 'Linux x86_64'
        elif 'Android' in ua:
            expected_platform = 'Linux armv8l'
        
        # 如果不一致,修正platform
        if expected_platform and platform != expected_platform:
            logger.warning(f"UA({ua[:50]})与Platform({platform})不一致, 修正为{expected_platform}")
            fingerprint['platform'] = expected_platform
        
        # 检查maxTouchPoints一致性
        max_touch = fingerprint.get('max_touch_points', 0)
        if 'Mobile' in ua or 'Android' in ua or 'iPhone' in ua:
            # 移动设备应该有触摸点
            if max_touch == 0:
                logger.warning("UA显示为移动设备但maxTouchPoints为0, 修正为5")
                fingerprint['max_touch_points'] = 5
        else:
            # 桌面设备不应该有触摸点(除非是触摸屏)
            if max_touch > 0:
                logger.warning("UA显示为桌面设备但maxTouchPoints>0, 修正为0")
                fingerprint['max_touch_points'] = 0
    
    def _check_locale_timezone_consistency(self, fingerprint: Dict[str, Any]) -> None:
        """检查语言与时区一致性"""
        locale = fingerprint.get('locale', 'zh-CN')
        timezone = fingerprint.get('timezone_id', 'Asia/Shanghai')
        
        # 中文locale应该配中国时区
        if locale.startswith('zh') and not timezone.startswith('Asia'):
            logger.warning(f"中文locale({locale})但时区({timezone})不在亚洲, 修正为Asia/Shanghai")
            fingerprint['timezone_id'] = 'Asia/Shanghai'
        
        # 检查语言列表一致性
        languages = fingerprint.get('languages', ['zh-CN', 'zh', 'en'])
        if isinstance(languages, list) and len(languages) > 0:
            if languages[0] != locale:
                logger.warning(f"主语言({languages[0]})与locale({locale})不一致, 修正")
                fingerprint['languages'] = [locale] + [lang for lang in languages if lang != locale]

    def _check_uach_consistency(self, fingerprint: Dict[str, Any]) -> None:
        """检查 UA-CH（navigator.userAgentData）与 UA/Platform 的一致性。"""
        ua = fingerprint.get("user_agent") or ""
        platform = fingerprint.get("platform", "Win32")
        ua_ch = fingerprint.get("ua_ch")
        if not isinstance(ua_ch, dict):
            return

        # 1) 修正 ua_ch.platform 与 platform 对齐（Win32/MacIntel/Linux* -> Windows/macOS/Linux）
        def _platform_to_uach(p: str) -> str:
            if p == "MacIntel":
                return "macOS"
            if isinstance(p, str) and p.startswith("Linux"):
                return "Linux"
            return "Windows"

        expected_uach_platform = _platform_to_uach(platform)
        if ua_ch.get("platform") != expected_uach_platform:
            logger.warning("ua_ch.platform(%s) 与 platform(%s) 不一致, 修正为 %s",
                           ua_ch.get("platform"), platform, expected_uach_platform)
            ua_ch["platform"] = expected_uach_platform

        # 2) 若 UA 明确是 Windows/Mac/Linux，则进一步校验 ua_ch.platform
        if "Windows" in ua and ua_ch.get("platform") != "Windows":
            logger.warning("UA 显示 Windows 但 ua_ch.platform=%s, 修正为 Windows", ua_ch.get("platform"))
            ua_ch["platform"] = "Windows"
        if ("Mac" in ua or "Macintosh" in ua) and ua_ch.get("platform") != "macOS":
            logger.warning("UA 显示 macOS 但 ua_ch.platform=%s, 修正为 macOS", ua_ch.get("platform"))
            ua_ch["platform"] = "macOS"
        if ("Linux" in ua and "Android" not in ua) and ua_ch.get("platform") != "Linux":
            logger.warning("UA 显示 Linux 但 ua_ch.platform=%s, 修正为 Linux", ua_ch.get("platform"))
            ua_ch["platform"] = "Linux"

        # 3) brands 基本结构兜底
        brands = ua_ch.get("brands")
        if not isinstance(brands, list) or not brands:
            ua_ch["brands"] = [
                {"brand": "Not.A/Brand", "version": "99"},
                {"brand": "Chromium", "version": "122"},
                {"brand": "Google Chrome", "version": "122"},
            ]

        # 4) mobile 字段兜底：桌面默认 False
        if "mobile" not in ua_ch:
            ua_ch["mobile"] = False

        fingerprint["ua_ch"] = ua_ch


def validate_fingerprint(fingerprint: Dict[str, Any]) -> Dict[str, Any]:
    """验证并修复指纹配置
    
    这是一个便捷函数,用于快速验证指纹
    
    Args:
        fingerprint: 指纹配置字典
        
    Returns:
        修复后的指纹配置
    """
    checker = FingerprintConsistencyChecker()
    return checker.check_and_fix(fingerprint)
