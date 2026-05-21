from __future__ import annotations

import ctypes
import logging
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication


def configure_windows_app_user_model_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "wemedia_baby.client.1.0.1.force_refresh"
        )
    except Exception:
        pass


def configure_high_dpi_policy() -> None:
    if hasattr(QApplication, "setHighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )


def create_application() -> QApplication:
    configure_high_dpi_policy()
    app = QApplication(sys.argv)
    from config.feature_flags import FeatureFlags

    app.setApplicationName(
        "媒小宝 吾爱破解论坛特别版" if FeatureFlags.is_52pojie() else "媒小宝"
    )
    from src.version import __version__

    app.setApplicationVersion(__version__)
    return app


def apply_picker_patches() -> None:
    try:
        from src.ui.patches.picker_confirm_right import apply_picker_confirm_right
        from src.ui.patches.picker_item_mask_align import apply_picker_item_mask_align
        from src.ui.patches.picker_item_mask_drawtext import apply_picker_item_mask_drawtext_safe

        apply_picker_confirm_right()
        apply_picker_item_mask_align()
        apply_picker_item_mask_drawtext_safe()
    except Exception as e:
        logging.debug("picker patches skipped: %s", e)


def initialize_theme_manager() -> None:
    try:
        from src.ui.styles.theme_manager import get_theme_manager

        get_theme_manager()
        logging.info("Theme manager initialized")
    except Exception as e:
        logging.error("Theme manager initialization failed: %s", e)
        try:
            from qfluentwidgets import Theme, setTheme

            setTheme(Theme.AUTO)
        except Exception:
            pass


def set_application_icon(app: QApplication) -> None:
    from src.infrastructure.common.path_manager import PathManager

    project_root = str(PathManager.get_resource_dir())
    icon_path_ico = os.path.join(project_root, "resources", "icons", "app.ico")
    icon_path_png = os.path.join(project_root, "resources", "logo.png")

    icon_to_use = None
    if os.path.exists(icon_path_png):
        icon_to_use = icon_path_png
        logging.info("Found PNG app icon: %s", icon_path_png)
    elif os.path.exists(icon_path_ico):
        icon_to_use = icon_path_ico
        logging.info("Found ICO app icon: %s", icon_path_ico)

    if not icon_to_use:
        logging.warning("No application icon file found")
        return

    app_icon = QIcon(icon_to_use)
    if app_icon.isNull():
        logging.error("Failed to load application icon: %s", icon_to_use)
        return
    app.setWindowIcon(app_icon)
    logging.info("Application icon set: %s", icon_to_use)
