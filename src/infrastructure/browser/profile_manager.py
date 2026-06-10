"""
账号凭证与指纹配置管理器
文件路径：src/infrastructure/browser/profile_manager.py
功能：管理 storage_state.json（关闭浏览器时导出快照）与 fingerprint_config.json（浏览器指纹）
"""

import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Optional, Dict, Any
from src.infrastructure.browser.automation_api import BrowserContext

logger = logging.getLogger(__name__)


# 常见的屏幕分辨率列表
COMMON_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
]


class ProfileManager:
    """账号凭证与指纹配置管理器
    
    职责：
    1. 关闭/导出时写入 storage_state.json（快照，不作为启动时灌入来源）
    2. 管理 fingerprint_config.json (UA, Viewport, Locale)
    3. 确保每个账号有独立的持久化目录
    """
    
    def __init__(self, account_id: str, platform: str, account_name: str, fingerprint_config: Optional[dict] = None, profile_folder_name: Optional[str] = None):
        """初始化
        
        Args:
            account_id: 账号唯一标识 (如手机号或平台ID)
            platform: 平台名称 (如 douyin)，必填
            account_name: 平台用户名，必填
            fingerprint_config: 指纹配置，None则随机生成
            profile_folder_name: 持久化的唯一指纹文件夹名 (如 profile_xxx)，避免因改名建新文件夹
        """
        if not platform or not account_name:
            raise ValueError(
                f"ProfileManager 初始化失败：platform 和 account_name 均为必填项，"
                f"当前 platform={platform!r}, account_name={account_name!r}"
            )

        self.account_id = account_id
        self.profile_folder_name = profile_folder_name

        from src.infrastructure.common.path_manager import PathManager
        account_root = PathManager.get_platform_account_dir(platform, account_name, profile_folder_name)
        self.base_dir = account_root / 'browser'
        
        # 确保目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 文件路径
        self.storage_state_path = self.base_dir / 'storage_state.json'
        self.fingerprint_path = self.base_dir / 'fingerprint_config.json'
        self.user_data_dir = self.base_dir / 'user_data'
        
        # 如果提供了自定义指纹配置，生成并保存
        if fingerprint_config is not None:
            logger.info(f"使用自定义指纹配置初始化: {account_name}")
            self.generate_fingerprint(fingerprint_config)
            
        logger.debug(f"ProfileManager 初始化: account={account_name}, platform={platform}, base_dir={self.base_dir}")

    
    async def save_storage_state(self, context: BrowserContext) -> bool:
        """保存浏览器上下文的 storage_state
        
        Args:
            context: Playwright BrowserContext 实例
            
        Returns:
            是否保存成功
        """
        try:
            # 使用 Playwright 内置方法导出
            await context.storage_state(path=str(self.storage_state_path))
            logger.info(f"凭证已保存: {self.storage_state_path}")
            return True
        except Exception as e:
            err = str(e).lower()
            if (
                "has been closed" in err
                or ("target page" in err and "closed" in err)
                or "context or browser has been closed" in err
            ):
                logger.debug(
                    "保存凭证跳过: 浏览器上下文已关闭 (%s)", self.storage_state_path
                )
                return False
            logger.error("保存凭证失败: %s", e, exc_info=True)
            return False
    
    def get_storage_state_path(self) -> Optional[str]:
        """获取 storage_state 文件路径 (如果存在)
        
        Returns:
            文件路径字符串，不存在则返回 None
        """
        if self.storage_state_path.exists():
            return str(self.storage_state_path)
        return None
    
    def get_fingerprint(self) -> Dict[str, Any]:
        """获取指纹配置，若不存在则生成默认配置
        
        Returns:
            指纹配置字典，包含 user_agent, viewport, locale, timezone 等
        """
        if self.fingerprint_path.exists():
            try:
                with open(self.fingerprint_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # 检查并补全缺失的字段 (针对旧版本指纹文件)
                is_dirty = False
                
                # 1. 补全硬件并发数
                if "hardware_concurrency" not in config:
                    config["hardware_concurrency"] = random.choice([4, 8, 12, 16])
                    is_dirty = True
                    
                # 2. 补全设备内存
                if "device_memory" not in config:
                    config["device_memory"] = random.choice([4, 8, 16, 32])
                    is_dirty = True
                    
                # 3. WebGL 厂商与渲染器（成对补全，且 vendor 由 renderer 推导）
                from .hardware_profiles import complete_webgl_fields

                if complete_webgl_fields(config):
                    is_dirty = True

                # 3b. cpu_model 由 validate_fingerprint._ensure_cpu_model 从整机档案写入（此处不写占位文案）

                # 4. 补全 Canvas 噪声种子
                if "canvas_noise_seed" not in config:
                    config["canvas_noise_seed"] = random.randint(1, 1000000)
                    is_dirty = True

                # 5. 补全 languages（兼容旧 profile 元数据）
                if "languages" not in config or not isinstance(config.get("languages"), list) or not config.get("languages"):
                    locale = config.get("locale", "zh-CN") or "zh-CN"
                    # 简单规则：中文默认带 en 作为次选；其他 locale 兜底为 [locale, "en"]
                    if isinstance(locale, str) and locale.lower().startswith("zh"):
                        config["languages"] = [locale, "zh", "en"]
                    else:
                        config["languages"] = [locale, "en"]
                    is_dirty = True

                # 6. 补全 ua_ch（Client Hints / UA-CH），与 UA/Platform 对齐
                if "ua_ch" not in config or not isinstance(config.get("ua_ch"), dict) or not config.get("ua_ch"):
                    ua = config.get("user_agent") or ""
                    plat = config.get("platform", "Win32")
                    config["ua_ch"] = self._generate_default_ua_ch(ua, plat)
                    is_dirty = True

                # 7. 补全 virtual_geo（环境 / 虚拟定位，与 IP 推断区分）
                from .virtual_geo import merge_virtual_geo_defaults_into_config

                if merge_virtual_geo_defaults_into_config(config):
                    is_dirty = True

                # 如果有更新，则保存回去
                if is_dirty:
                    logger.info(f"升级旧版指纹配置，补全硬件参数: {self.fingerprint_path}")
                    self.save_fingerprint(config)

                # 每次加载后做一致性校验（修正 vendor/renderer、显卡与内存等）
                from .fingerprint_checker import validate_fingerprint

                _before = json.dumps(config, sort_keys=True, ensure_ascii=False)
                validate_fingerprint(config)
                _after = json.dumps(config, sort_keys=True, ensure_ascii=False)
                if _before != _after:
                    logger.info("指纹一致性校验已修正字段，写回: %s", self.fingerprint_path)
                    self.save_fingerprint(config)

                logger.debug(f"指纹配置已加载: {self.fingerprint_path}")
                return config
            except Exception as e:
                logger.warning(f"加载指纹配置失败，将重新生成: {e}")
        
        # 生成默认配置
        config = self._generate_default_fingerprint()
        # 确保默认生成也包含 languages/ua_ch（避免仅在“旧文件升级”路径补齐）
        try:
            locale = config.get("locale", "zh-CN") or "zh-CN"
            if not isinstance(config.get("languages"), list) or not config.get("languages"):
                if isinstance(locale, str) and locale.lower().startswith("zh"):
                    config["languages"] = [locale, "zh", "en"]
                else:
                    config["languages"] = [locale, "en"]
            if not isinstance(config.get("ua_ch"), dict) or not config.get("ua_ch"):
                config["ua_ch"] = self._generate_default_ua_ch(config.get("user_agent") or "", config.get("platform", "Win32"))
        except Exception:
            pass
        # 一致性检查后再保存
        from .fingerprint_checker import validate_fingerprint
        config = validate_fingerprint(config)
        self.save_fingerprint(config)
        return config

    @staticmethod
    def _parse_chrome_major(user_agent: str) -> Optional[str]:
        try:
            m = re.search(r"Chrome/(\d+)\.", user_agent or "")
            return m.group(1) if m else None
        except Exception:
            return None

    @staticmethod
    def _ua_ch_platform_from_platform(platform: str) -> str:
        p = (platform or "").strip()
        if p == "MacIntel":
            return "macOS"
        if p.startswith("Linux"):
            return "Linux"
        return "Windows"

    def _generate_default_ua_ch(self, user_agent: str, platform: str) -> Dict[str, Any]:
        """生成默认 UA-CH（尽量与 UA/Platform 一致）。"""
        major = self._parse_chrome_major(user_agent) or "122"
        ua_ch_platform = self._ua_ch_platform_from_platform(platform)
        brands = [
            {"brand": "Not.A/Brand", "version": "99"},
            {"brand": "Chromium", "version": str(major)},
            {"brand": "Google Chrome", "version": str(major)},
        ]
        return {
            "brands": brands,
            "mobile": False,
            "platform": ua_ch_platform,
            # 高熵字段（尽力而为，保持合理即可）
            "architecture": "x86",
            "bitness": "64",
            "model": "",
            "platformVersion": "10.0.0",
            "uaFullVersion": f"{major}.0.0.0",
            "fullVersionList": [
                {"brand": "Not.A/Brand", "version": "99.0.0.0"},
                {"brand": "Chromium", "version": f"{major}.0.0.0"},
                {"brand": "Google Chrome", "version": f"{major}.0.0.0"},
            ],
        }
    
    def generate_fingerprint(self, custom_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """生成指纹配置(支持自定义)
        
        Args:
            custom_config: 用户自定义配置,None则随机生成
            
        Returns:
            指纹配置字典
        """
        if custom_config is None:
            # 随机生成
            logger.info("使用随机生成指纹")
            config = self._generate_default_fingerprint()
        else:
            # 使用用户配置
            logger.info(f"使用自定义指纹配置: {custom_config.keys()}")
            base_config = self._generate_default_fingerprint()
            # 兼容旧字段：canvas_noise -> canvas_noise_strength
            try:
                if "canvas_noise_strength" not in custom_config and "canvas_noise" in custom_config:
                    custom_config = dict(custom_config)
                    custom_config["canvas_noise_strength"] = custom_config.get("canvas_noise")
            except Exception:
                pass

            # 用自定义配置覆盖
            base_config.update(custom_config)
            config = base_config

        # Canvas 噪声：确保 strength 与 seed 都存在且可用
        # - strength: 用户语义（低/中/高的强度值或数值）
        # - seed: 脚本使用的稳定种子（同一账号应保持稳定）
        try:
            strength = config.get("canvas_noise_strength")
            if strength is None and "canvas_noise" in config:
                strength = config.get("canvas_noise")
                config["canvas_noise_strength"] = strength
            # 规范化 strength 为 float（无效则移除，使用默认）
            if strength is not None:
                try:
                    config["canvas_noise_strength"] = float(strength)
                except Exception:
                    config.pop("canvas_noise_strength", None)
            # 确保 seed 存在（默认指纹已生成；这里做兜底）
            if "canvas_noise_seed" not in config:
                config["canvas_noise_seed"] = random.randint(1, 1000000)
        except Exception:
            pass

        # languages/ua_ch：确保存在并与 locale/UA/Platform 至少不冲突
        try:
            locale = config.get("locale", "zh-CN") or "zh-CN"
            languages = config.get("languages")
            if not isinstance(languages, list) or not languages:
                if isinstance(locale, str) and locale.lower().startswith("zh"):
                    config["languages"] = [locale, "zh", "en"]
                else:
                    config["languages"] = [locale, "en"]
            if not isinstance(config.get("ua_ch"), dict) or not config.get("ua_ch"):
                config["ua_ch"] = self._generate_default_ua_ch(config.get("user_agent") or "", config.get("platform", "Win32"))
        except Exception:
            pass

        try:
            from .virtual_geo import merge_virtual_geo_defaults_into_config

            merge_virtual_geo_defaults_into_config(config)
        except Exception:
            pass
        
        # 一致性检查
        from .fingerprint_checker import validate_fingerprint
        config = validate_fingerprint(config)
        
        # 保存配置
        self.save_fingerprint(config)
        return config

    
    def save_fingerprint(self, config: Dict[str, Any]) -> bool:
        """保存指纹配置（原子写入：先写临时文件再 rename，防止崩溃导致半截 JSON）
        
        Args:
            config: 指纹配置字典
            
        Returns:
            是否保存成功
        """
        import tempfile
        try:
            dir_name = str(self.fingerprint_path.parent)
            os.makedirs(dir_name, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as tmp_f:
                    json.dump(config, tmp_f, ensure_ascii=False, indent=2)
                    tmp_f.flush()
                    os.fsync(tmp_f.fileno())
                os.replace(tmp_path, str(self.fingerprint_path))
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.info(f"指纹配置已保存: {self.fingerprint_path}")
            return True
        except Exception as e:
            logger.error(f"保存指纹配置失败: {e}", exc_info=True)
            return False
    
    def _generate_default_fingerprint(self) -> Dict[str, Any]:
        """生成默认指纹配置
        
        注意：UA 版本将在 BrowserManager 启动时动态对齐到实际内核版本
        
        Returns:
            默认指纹配置字典
        """
        # 默认 viewport 为 None，让浏览器自适应窗口大小
        viewport = None
        
        # 常见屏幕分辨率池
        screen_resolutions = [
            {"width": 1920, "height": 1080},
            {"width": 2560, "height": 1440},
            {"width": 1366, "height": 768},
            {"width": 1536, "height": 864},
            {"width": 3840, "height": 2160},
        ]
        screen = random.choice(screen_resolutions)

        from .hardware_profiles import pick_random_hardware_bundle

        hw = pick_random_hardware_bundle()

        config = {
            # UA 占位符，将在 BrowserManager 中根据实际浏览器版本动态填充，这里先给一个默认值通过检查
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "viewport": viewport,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "color_scheme": "light",
            "device_scale_factor": 1.0,
            
            # --- Canvas 指纹 ---
            # Canvas 噪声种子 (每个账号固定，确保指纹一致性)
            "canvas_noise_seed": random.randint(1, 1000000),
            
            # --- 硬件参数指纹（整机档案同档：CPU / 内存 / 显卡 / 型号）---
            "hardware_concurrency": hw["hardware_concurrency"],
            "device_memory": hw["device_memory"],
            "cpu_model": hw["cpu_model"],
            "webgl_vendor": hw["webgl_vendor"],
            "webgl_renderer": hw["webgl_renderer"],
            
            # --- Screen 屏幕指纹 ---
            "screen_width": screen["width"],
            "screen_height": screen["height"],
            "screen_avail_width": screen["width"],
            "screen_avail_height": screen["height"] - 40,  # 减去任务栏高度
            "screen_color_depth": 24,
            "screen_pixel_depth": 24,
            
            # --- AudioContext 音频指纹 ---
            "audio_context_seed": random.randint(1, 1000000),
            
            # --- Battery API ---
            "battery_charging": True,
            "battery_level": round(random.uniform(0.5, 1.0), 2),
            
            # --- Navigator 扩展属性 ---
            "platform": "Win32",
            "max_touch_points": 0,
            "vendor": "Google Inc.",
            "vendor_sub": "",
            "product_sub": "20030107",

            # --- Languages（与 locale 对齐，供 stealth 注入/headers 对齐使用） ---
            "languages": ["zh-CN", "zh", "en"],
            
            # --- Connection 网络连接 ---
            "connection_effective_type": random.choice(["4g", "wifi"]),
            "connection_downlink": random.choice([10, 20, 50, 100]),
            "connection_rtt": random.randint(20, 100),

            # --- 环境 / 虚拟定位（经纬度由用户或后续 UI 配置；启用后对浏览器 Geolocation 生效）---
            "virtual_geo": {
                "enabled": False,
                "label": "",
                "latitude": None,
                "longitude": None,
                "accuracy": 50.0,
            },
        }
        # UA-CH（Client Hints）默认值
        try:
            config["ua_ch"] = self._generate_default_ua_ch(config.get("user_agent") or "", config.get("platform", "Win32"))
        except Exception:
            pass
        
        logger.info(f"生成默认指纹配置: viewport={viewport}, screen={screen['width']}x{screen['height']}")
        
        # 一致性检查
        from .fingerprint_checker import validate_fingerprint
        config = validate_fingerprint(config)
        
        return config
    
    def get_user_data_dir(self) -> str:
        """获取 user_data_dir 路径
        
        Returns:
            用户数据目录路径
        """
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        return str(self.user_data_dir)
    
    def _user_data_has_chrome_cookie_store(self) -> bool:
        """持久化 user_data 下是否已有非空的 Chromium Cookie 库。"""
        ud = self.user_data_dir
        if not ud.is_dir():
            return False
        for rel in ("Default/Network/Cookies", "Default/Cookies"):
            p = ud / rel
            try:
                if p.is_file() and p.stat().st_size > 0:
                    return True
            except OSError:
                continue
        return False

    def has_valid_credentials(self) -> bool:
        """是否存在可用的登录凭证：账号根目录 cookies.json 或持久化 profile 内 Cookie 库。"""
        cookies_json = self.base_dir.parent / "cookies.json"
        if cookies_json.is_file():
            return True
        return self._user_data_has_chrome_cookie_store()
