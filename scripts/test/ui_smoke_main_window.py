#!/usr/bin/env python3
"""
无头/CI 冒烟：创建 QApplication，构造 MainWindow，show → processEvents → close。

用法（仓库根目录）:
  python scripts/test/ui_smoke_main_window.py

Linux CI 建议:
  export QT_QPA_PLATFORM=offscreen
"""

from __future__ import annotations

import os
import sys
import traceback


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        try:
            from src.ui.styles.theme_manager import get_theme_manager

            get_theme_manager()
        except Exception as e:
            print(f"[ui_smoke] theme_manager skip: {e}", file=sys.stderr)

        from src.ui.main_window import MainWindow

        w = MainWindow()
        w.show()
        app.processEvents()
        w.close()
        app.processEvents()
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

