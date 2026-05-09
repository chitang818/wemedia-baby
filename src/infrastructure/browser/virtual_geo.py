"""
指纹 virtual_geo：环境 / 虚拟定位配置。

与「出口 IP 地理库推断」区分：IP 归属常为运营商接入点，不等于用户真实城市；
启用 virtual_geo 并填写经纬度后，由 Playwright 对浏览器上下文注入 Geolocation，供后续站点与展示一致。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

DEFAULT_VIRTUAL_GEO: Dict[str, Any] = {
    "enabled": False,
    "label": "",
    "latitude": None,
    "longitude": None,
    "accuracy": 50.0,
}


def coalesce_virtual_geo(fingerprint: Dict[str, Any]) -> Dict[str, Any]:
    """从指纹字典解析出规整的 virtual_geo（不修改原 dict）。"""
    out = dict(DEFAULT_VIRTUAL_GEO)
    raw = fingerprint.get("virtual_geo")
    if not isinstance(raw, dict):
        return out
    out["enabled"] = bool(raw.get("enabled"))
    out["label"] = str(raw.get("label") or "").strip()

    def _coord(name: str) -> Optional[float]:
        v = raw.get(name)
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    out["latitude"] = _coord("latitude")
    out["longitude"] = _coord("longitude")
    acc_raw = raw.get("accuracy")
    if acc_raw is None or acc_raw == "":
        out["accuracy"] = float(DEFAULT_VIRTUAL_GEO["accuracy"])
    else:
        try:
            out["accuracy"] = max(1.0, float(acc_raw))
        except (TypeError, ValueError):
            out["accuracy"] = float(DEFAULT_VIRTUAL_GEO["accuracy"])
    return out


def merge_virtual_geo_defaults_into_config(config: Dict[str, Any]) -> bool:
    """为 fingerprint_config 补全 virtual_geo 缺省字段；有修改返回 True。"""
    changed = False
    raw = config.get("virtual_geo")
    if not isinstance(raw, dict):
        config["virtual_geo"] = {k: v for k, v in DEFAULT_VIRTUAL_GEO.items()}
        return True
    for k, v in DEFAULT_VIRTUAL_GEO.items():
        if k not in raw:
            raw[k] = v
            changed = True
    return changed


def build_playwright_geolocation(fingerprint: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """若启用且经纬度有效，返回供 context.set_geolocation 使用的字典。"""
    vg = coalesce_virtual_geo(fingerprint)
    if not vg["enabled"]:
        return None
    lat, lon = vg.get("latitude"), vg.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0):
        return None
    acc = vg.get("accuracy")
    try:
        acc_f = float(acc) if acc is not None else float(DEFAULT_VIRTUAL_GEO["accuracy"])
    except (TypeError, ValueError):
        acc_f = float(DEFAULT_VIRTUAL_GEO["accuracy"])
    acc_f = max(1.0, min(acc_f, 10_000.0))
    return {"latitude": la, "longitude": lo, "accuracy": acc_f}
