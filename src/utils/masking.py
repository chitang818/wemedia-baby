"""
数据脱敏工具函数
功能：对敏感数据（用户名、IP、Token、Cookie 等）进行脱敏处理，供日志输出使用。
"""


def mask_username(username: str) -> str:
    """用户名脱敏：保留首尾字符，中间用 * 替代。"""
    if not username:
        return ""
    if len(username) <= 2:
        return username[0] + "*"
    return username[0] + "*" * (len(username) - 2) + username[-1]


def mask_ip(ip: str) -> str:
    """IP 地址脱敏：IPv4 保留前两段，后两段替换为 *.*。"""
    if not ip:
        return ""
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.*.*"
    # IPv6 或其他格式，只保留前 6 个字符
    if len(ip) > 6:
        return ip[:6] + "***"
    return ip


def mask_token(token: str) -> str:
    """Token 脱敏：保留首尾各 3 位，中间用 ... 替代。"""
    if not token:
        return ""
    if len(token) <= 8:
        return token[:2] + "***"
    return token[:3] + "..." + token[-3:]


def mask_cookie_domain(cookie_data) -> str:
    """Cookie 脱敏：仅显示域名和过期时间，隐藏 value。"""
    if not cookie_data:
        return "<empty>"
    if isinstance(cookie_data, list):
        domains = set()
        for c in cookie_data:
            if isinstance(c, dict):
                d = c.get("domain") or c.get("Domain") or "?"
                domains.add(d)
        return f"[{len(cookie_data)} cookies, domains={','.join(sorted(domains))}]"
    if isinstance(cookie_data, dict):
        return f"domain={cookie_data.get('domain', '?')}"
    return "<masked>"
