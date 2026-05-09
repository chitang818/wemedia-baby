"""
兼容入口：scripts/run_tests.py

真实脚本已迁移到：scripts/test/run_tests.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / "scripts" / "test" / "run_tests.py"
    os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
