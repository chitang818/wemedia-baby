"""
下载热门平台图标（Simple Icons，CC0）并保存为 PNG，供添加账号对话框使用。
运行：在项目根目录执行  python scripts/dev/download_platform_icons.py
"""

import os
import sys
import urllib.request

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "resources", "icons", "platform")
CDN = "https://cdn.jsdelivr.net/npm/simple-icons@v11/icons"

# platform_id -> simple-icons slug（可多试几个）
SLUGS = {
    "douyin": ["douyin", "tiktok"],
    "wechat_video": ["wechat"],
    "kuaishou": ["kuaishou"],
    "xiaohongshu": ["xiaohongshu"],
    "bilibili": ["bilibili"],
    "toutiao": ["toutiao", "jinritoutiao", "bytedance"],
    "baijiahao": ["baidu"],
    "weibo": ["sinaweibo", "weibo"],
    "duoduoshipin": ["pinduoduo"],
    "qiehao": ["tencentqq"],
}


def download_svg(slug: str) -> bytes:
    url = f"{CDN}/{slug}.svg"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


def svg_to_png(svg_bytes: bytes, out_path: str, size: int = 128) -> bool:
    try:
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QImage, QPainter
    except ImportError:
        print("需要 PySide6（含 QtSvg）才能将 SVG 转为 PNG，请安装后重试。")
        return False
    r = QSvgRenderer(svg_bytes)
    if not r.isValid():
        return False
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    r.render(painter)
    painter.end()
    return img.save(out_path, "PNG")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for platform_id, slugs in SLUGS.items():
        out_path = os.path.join(OUT_DIR, f"{platform_id}.png")
        done = False
        for slug in slugs:
            try:
                svg_bytes = download_svg(slug)
                if svg_to_png(svg_bytes, out_path):
                    print(f"OK: {platform_id} <- {slug}")
                    done = True
                    break
            except Exception as e:
                print(f"跳过 {platform_id}/{slug}: {e}")
        if not done:
            print(f"未生成: {platform_id}.png，请手动放置到 {OUT_DIR}")
    print("完成。图标目录:", OUT_DIR)


if __name__ == "__main__":
    main()
    sys.exit(0)

