"""
兼容入口：scripts/download_platform_icons.py

真实脚本已迁移到：scripts/dev/download_platform_icons.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / "scripts" / "dev" / "download_platform_icons.py"
    os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
