"""
整机硬件档案（指纹用）
路径：src/infrastructure/browser/hardware_profiles.py
功能：按档位生成一致的 CPU/内存/WebGL；由 webgl_renderer 推导 webgl_vendor（Chromium/ANGLE 常见格式）。
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Legacy profile fallback values retained for old account metadata compatibility.
DEFAULT_WEBGL_RENDERER = (
    "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"
)


def derive_webgl_vendor(webgl_renderer: str) -> str:
    """根据 ANGLE 渲染器字符串推导 UNMASKED_VENDOR_WEBGL（Chromium 常见写法）。"""
    r = (webgl_renderer or "").strip()
    if not r:
        return "Google Inc. (NVIDIA)"
    m = re.match(r"ANGLE\s*\(\s*([^,]+)\s*,", r, re.IGNORECASE)
    if not m:
        logger.warning("无法从 webgl_renderer 解析厂商，回退 NVIDIA: %s", r[:80])
        return "Google Inc. (NVIDIA)"
    inner = m.group(1).strip().upper()
    if "NVIDIA" in inner:
        return "Google Inc. (NVIDIA)"
    if "AMD" in inner or "ATI" in inner:
        return "Google Inc. (AMD)"
    if "INTEL" in inner:
        return "Google Inc. (Intel)"
    if "APPLE" in inner:
        return "Google Inc. (Apple)"
    logger.warning("webgl_renderer 厂商段未识别(%s)，回退 NVIDIA", inner)
    return "Google Inc. (NVIDIA)"


def default_webgl_vendor() -> str:
    return derive_webgl_vendor(DEFAULT_WEBGL_RENDERER)


# 档位 key 与 UI「整机档位」一致
TIER_ENTRY = "entry"
TIER_MAINSTREAM = "mainstream"
TIER_HIGH = "high"

# 每条：同一档内 CPU/内存/显卡/型号一致（hardware_concurrency 与浏览器 navigator.hardwareConcurrency 一致，多为逻辑核心数）
_HARDWARE_VARIANTS: List[Dict[str, Any]] = [
    # --- 入门 ---
    {
        "tier": TIER_ENTRY,
        "hardware_concurrency": 4,
        "device_memory": 8,
        "cpu_model": "Intel Core i3-10100",
        "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_ENTRY,
        "hardware_concurrency": 4,
        "device_memory": 8,
        "cpu_model": "Intel Core i3-12100",
        "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 730 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_ENTRY,
        "hardware_concurrency": 4,
        "device_memory": 8,
        "cpu_model": "Intel Pentium Gold G6400",
        "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 610 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_ENTRY,
        "hardware_concurrency": 4,
        "device_memory": 4,
        "cpu_model": "AMD Athlon 3000G",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon(TM) Vega 3 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_ENTRY,
        "hardware_concurrency": 4,
        "device_memory": 8,
        "cpu_model": "AMD Ryzen 3 3200G",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon Vega 8 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_ENTRY,
        "hardware_concurrency": 6,
        "device_memory": 8,
        "cpu_model": "AMD Ryzen 5 5500",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    # --- 主流 ---
    {
        "tier": TIER_MAINSTREAM,
        "hardware_concurrency": 8,
        "device_memory": 16,
        "cpu_model": "Intel Core i5-10400",
        "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_MAINSTREAM,
        "hardware_concurrency": 8,
        "device_memory": 16,
        "cpu_model": "Intel Core i5-11400",
        "webgl_renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_MAINSTREAM,
        "hardware_concurrency": 8,
        "device_memory": 16,
        "cpu_model": "Intel Core i5-12400",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_MAINSTREAM,
        "hardware_concurrency": 8,
        "device_memory": 16,
        "cpu_model": "Intel Core i5-13400",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_MAINSTREAM,
        "hardware_concurrency": 8,
        "device_memory": 16,
        "cpu_model": "AMD Ryzen 5 3600",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_MAINSTREAM,
        "hardware_concurrency": 8,
        "device_memory": 16,
        "cpu_model": "AMD Ryzen 5 5600",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_MAINSTREAM,
        "hardware_concurrency": 12,
        "device_memory": 16,
        "cpu_model": "AMD Ryzen 5 5600X",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon RX 6600 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_MAINSTREAM,
        "hardware_concurrency": 12,
        "device_memory": 32,
        "cpu_model": "Intel Core i7-10700",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    # --- 高端 ---
    {
        "tier": TIER_HIGH,
        "hardware_concurrency": 12,
        "device_memory": 32,
        "cpu_model": "AMD Ryzen 7 5800X",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_HIGH,
        "hardware_concurrency": 16,
        "device_memory": 32,
        "cpu_model": "AMD Ryzen 7 7700X",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon RX 7800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_HIGH,
        "hardware_concurrency": 16,
        "device_memory": 32,
        "cpu_model": "Intel Core i7-12700K",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_HIGH,
        "hardware_concurrency": 16,
        "device_memory": 32,
        "cpu_model": "Intel Core i7-13700",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_HIGH,
        "hardware_concurrency": 16,
        "device_memory": 32,
        "cpu_model": "Intel Core i9-12900K",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_HIGH,
        "hardware_concurrency": 24,
        "device_memory": 32,
        "cpu_model": "AMD Ryzen 9 5900X",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "tier": TIER_HIGH,
        "hardware_concurrency": 32,
        "device_memory": 64,
        "cpu_model": "AMD Ryzen 9 7950X",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
]


def list_tiers() -> List[str]:
    return [TIER_ENTRY, TIER_MAINSTREAM, TIER_HIGH]


def list_display_presets() -> List[Dict[str, Any]]:
    """供界面或其它模块枚举「真实整机方案」（含档位说明，不含内部实现细节）。"""
    out: List[Dict[str, Any]] = []
    for v in _HARDWARE_VARIANTS:
        b = _fingerprint_bundle_from_variant(v.copy())
        b["tier"] = v["tier"]
        b["tier_name"] = tier_display_name(v["tier"])
        out.append(b)
    return out


def tier_display_name(tier: str) -> str:
    return {
        TIER_ENTRY: "入门办公（核显 / 入门独显）",
        TIER_MAINSTREAM: "主流性能（中端独显）",
        TIER_HIGH: "高端配置（高端独显与大内存）",
    }.get(tier, tier)


def _variants_for_tier(tier: str) -> List[Dict[str, Any]]:
    return [v.copy() for v in _HARDWARE_VARIANTS if v["tier"] == tier]


def _fingerprint_bundle_from_variant(variant: Dict[str, Any]) -> Dict[str, Any]:
    """写入 fingerprint_config 的字段（不含内部 tier 标记）。"""
    b = {k: v for k, v in variant.items() if k != "tier"}
    b["webgl_vendor"] = derive_webgl_vendor(b["webgl_renderer"])
    return b


def pick_random_hardware_bundle(tier: Optional[str] = None) -> Dict[str, Any]:
    """随机抽一套整机参数（含 webgl_renderer）；webgl_vendor 由 derive_webgl_vendor 得到。"""
    if tier is None:
        tier = random.choice(list_tiers())
    pool = _variants_for_tier(tier)
    if not pool:
        pool = [v.copy() for v in _HARDWARE_VARIANTS]
    return _fingerprint_bundle_from_variant(random.choice(pool))


def pick_hardware_bundle_for_tier(tier: str) -> Dict[str, Any]:
    """指定档位随机变体（供添加账号「自定义」整机档位）。"""
    pool = _variants_for_tier(tier)
    if not pool:
        return pick_random_hardware_bundle(None)
    return _fingerprint_bundle_from_variant(random.choice(pool))


def _normalize_gpu_family_hint(vendor_str: str) -> Optional[str]:
    s = (vendor_str or "").upper()
    if "NVIDIA" in s:
        return "NVIDIA"
    if "INTEL" in s:
        return "INTEL"
    if "APPLE" in s:
        return "APPLE"
    if "AMD" in s or "ATI" in s:
        return "AMD"
    return None


def _all_renderers_by_family(family: str) -> List[str]:
    fam = family.upper()
    out: List[str] = []
    for v in _HARDWARE_VARIANTS:
        r = v["webgl_renderer"]
        m = re.match(r"ANGLE\s*\(\s*([^,]+)\s*,", r, re.IGNORECASE)
        if not m:
            continue
        inner = m.group(1).strip().upper()
        ok = False
        if fam == "NVIDIA" and "NVIDIA" in inner:
            ok = True
        elif fam == "AMD" and ("AMD" in inner or "ATI" in inner):
            ok = True
        elif fam == "INTEL" and "INTEL" in inner:
            ok = True
        elif fam == "APPLE" and "APPLE" in inner:
            ok = True
        if ok:
            out.append(r)
    return out


def pick_matching_renderer(webgl_vendor: str) -> Optional[str]:
    """根据现有 vendor 字符串选一条同族 renderer（用于只缺 renderer 的补全）。"""
    fam = _normalize_gpu_family_hint(webgl_vendor)
    if not fam:
        return None
    pool = _all_renderers_by_family(fam)
    if not pool:
        return None
    return random.choice(pool)


def complete_webgl_fields(config: Dict[str, Any]) -> bool:
    """补全/纠正 webgl_vendor 与 webgl_renderer。返回是否修改了 config。"""
    changed = False
    renderer = config.get("webgl_renderer")
    vendor = config.get("webgl_vendor")
    has_r = bool(renderer and str(renderer).strip())
    has_v = bool(vendor and str(vendor).strip())

    def _merge_hw_bundle(b: Dict[str, Any]) -> None:
        """写入整机档案字段，避免只补显卡导致 CPU/内存与显卡档位脱节。"""
        for k, v in b.items():
            config[k] = v

    if not has_r and has_v:
        r = pick_matching_renderer(str(vendor))
        if not r:
            b = pick_random_hardware_bundle()
            if (
                config.get("hardware_concurrency") is not None
                and config.get("device_memory") is not None
            ):
                config["webgl_renderer"] = b["webgl_renderer"]
                config["webgl_vendor"] = b["webgl_vendor"]
            else:
                _merge_hw_bundle(b)
            return True
        config["webgl_renderer"] = r
        renderer = r
        has_r = True
        changed = True

    if not has_r and not has_v:
        b = pick_random_hardware_bundle()
        has_hw = (
            config.get("hardware_concurrency") is not None
            and config.get("device_memory") is not None
        )
        if has_hw:
            config["webgl_renderer"] = b["webgl_renderer"]
            config["webgl_vendor"] = b["webgl_vendor"]
            cm = config.get("cpu_model")
            if not cm or not str(cm).strip():
                config["cpu_model"] = b.get("cpu_model", "")
        else:
            _merge_hw_bundle(b)
        return True

    expected = derive_webgl_vendor(str(renderer))
    if not has_v or str(vendor).strip() != expected:
        config["webgl_vendor"] = expected
        changed = True

    return changed


def infer_gpu_tier(webgl_renderer: str) -> str:
    """粗略分级：integrated / mid / high，供一致性校验。"""
    u = (webgl_renderer or "").upper()
    if any(
        x in u
        for x in (
            "UHD GRAPHICS",
            "UHD 6",
            "IRIS",
            "VEGA 3",
            "VEGA 8",
            "HD GRAPHICS",
        )
    ):
        return "integrated"
    # 先匹配高端子串，避免「3060 Ti」被当成中端「3060」
    if any(
        x in u
        for x in (
            "RTX 4090",
            "RTX 4080",
            "RTX 4070",
            "RTX 3090",
            "RTX 3080",
            "RTX 3070 TI",
            "RTX 3080 TI",
            "RTX 4060 TI",
            "RTX 4070 TI",
            "RTX 3060 TI",
            "RX 7900",
            "RX 7800",
            "RX 7700",
            "RX 7800",
            "RX 6950",
            "RX 6900",
            "RX 6800",
            "RX 6700 XT",
        )
    ):
        return "high"
    if any(
        x in u
        for x in (
            "RTX 3060",
            "RTX 3050",
            "RTX 2060",
            "RTX 2070",
            "GTX 1660",
            "GTX 1650",
            "GTX 1630",
            "RX 7600",
            "RX 6700",
            "RX 6600",
            "RX 6500",
            "RX 5700",
            "RX 5600",
        )
    ):
        return "mid"
    if "RTX" in u or "GTX" in u or "RADEON RX" in u:
        return "mid"
    return "integrated"


def is_placeholder_cpu_model(cpu_model: Optional[str]) -> bool:
    """是否为历史占位文案（需替换为档案中的真实型号）。"""
    if not cpu_model or not str(cpu_model).strip():
        return True
    s = str(cpu_model).strip()
    if "展示用" in s:
        return True
    if s.startswith("常见") and "处理器" in s:
        return True
    return False


def cpu_model_matches_current_hardware(
    cpu_model: str,
    hardware_concurrency: int,
    webgl_renderer: str,
) -> bool:
    """当前型号是否仍与逻辑核心数、显卡族（Google Inc. 前缀）一致。"""
    try:
        cores = int(hardware_concurrency)
    except (TypeError, ValueError):
        cores = 4
    r = (webgl_renderer or "").strip()
    for v in _HARDWARE_VARIANTS:
        if v["cpu_model"] != cpu_model:
            continue
        if v["hardware_concurrency"] != cores:
            return False
        if not r:
            return True
        if derive_webgl_vendor(v["webgl_renderer"]) != derive_webgl_vendor(r):
            return False
        return infer_gpu_tier(v["webgl_renderer"]) == infer_gpu_tier(r)
    return False


def _closest_concurrency(cores: int) -> int:
    all_c = sorted({v["hardware_concurrency"] for v in _HARDWARE_VARIANTS})
    if not all_c:
        return 8
    return min(all_c, key=lambda x: abs(x - cores))


def _pick_variant_candidates(
    hardware_concurrency: int,
    device_memory: int,
    webgl_renderer: str,
) -> List[Dict[str, Any]]:
    """按核心数、内存、显卡档次筛选档案，用于稳定挑选 CPU 型号。"""
    try:
        cores = int(hardware_concurrency)
    except (TypeError, ValueError):
        cores = 4
    try:
        mem = int(device_memory)
    except (TypeError, ValueError):
        mem = 8
    r = (webgl_renderer or "").strip()

    pool = [v for v in _HARDWARE_VARIANTS if v["hardware_concurrency"] == cores]
    if not pool:
        cc = _closest_concurrency(cores)
        pool = [v for v in _HARDWARE_VARIANTS if v["hardware_concurrency"] == cc]

    mem_match = [v for v in pool if v["device_memory"] == mem]
    if mem_match:
        pool = mem_match

    if r:
        rt = infer_gpu_tier(r)
        tier_match = [v for v in pool if infer_gpu_tier(v["webgl_renderer"]) == rt]
        if tier_match:
            pool = tier_match

    return pool


def resolve_cpu_model_for_fingerprint(
    hardware_concurrency: int,
    device_memory: int,
    webgl_renderer: str,
) -> str:
    """从整机档案中按当前硬件组合稳定选取真实 CPU 型号（同配置结果不变）。"""
    candidates = _pick_variant_candidates(
        hardware_concurrency, device_memory, webgl_renderer
    )
    if not candidates:
        candidates = list(_HARDWARE_VARIANTS)
    candidates_sorted = sorted(
        candidates, key=lambda x: (x["cpu_model"], x["webgl_renderer"])
    )
    try:
        cores = int(hardware_concurrency)
    except (TypeError, ValueError):
        cores = 4
    try:
        mem = int(device_memory)
    except (TypeError, ValueError):
        mem = 8
    key = f"{cores}|{mem}|{webgl_renderer or ''}"
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    pick = candidates_sorted[h % len(candidates_sorted)]
    return str(pick["cpu_model"])


def generic_cpu_model_for_cores(cores: int) -> str:
    """已无档案命中时的最后兜底（正常不应走到）。"""
    try:
        c = int(cores)
    except (TypeError, ValueError):
        c = 4
    return resolve_cpu_model_for_fingerprint(c, 16, DEFAULT_WEBGL_RENDERER)
