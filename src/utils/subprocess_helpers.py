"""
subprocess 辅助：Windows GUI 程序中调用外部 exe 时避免弹出控制台窗口。
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any, Dict


def subprocess_hide_window_kwargs() -> Dict[str, Any]:
    """供 subprocess.run / Popen 解包使用；非 Windows 返回空字典。"""
    if sys.platform != "win32":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if not flags:
        return {}
    return {"creationflags": flags}
