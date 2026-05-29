"""Shared media validation helpers for publish pipeline filters."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from src.infrastructure.common.pipeline.base_filter import PublishContext
from src.services.common.media_validator import MediaValidator

_FOLDER_MARKER_PREFIX = "__FOLDER__:"
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")


def _publish_file_type(context: PublishContext) -> str:
    explicit = (
        getattr(context, "publish_type", None)
        or getattr(context, "file_type", None)
        or ""
    )
    ft = str(explicit).strip().lower()
    if ft in ("video", "image"):
        return ft
    fp = str(getattr(context, "file_path", "") or "").strip().lower()
    return "image" if fp.endswith(_IMAGE_EXTS) else "video"


def _split_image_paths(file_path: str) -> list[str]:
    return [
        part.strip()
        for part in str(file_path or "").split(",")
        if part.strip() and not part.strip().startswith(_FOLDER_MARKER_PREFIX)
    ]


def _missing_message(paths: list[str]) -> Optional[str]:
    missing = [p for p in paths if not Path(p).is_file()]
    if not missing:
        return None
    if len(paths) == 1:
        return f"文件不存在: {paths[0]}"
    names = ", ".join(os.path.basename(p) for p in missing[:3])
    suffix = f" 等共 {len(missing)} 个" if len(missing) > 3 else ""
    return f"部分图片不存在: {names}{suffix}"


def validate_publish_media(
    context: PublishContext,
    media_validator: MediaValidator,
) -> Optional[str]:
    """Return an error message when media validation fails, otherwise None."""
    file_path = str(getattr(context, "file_path", "") or "")
    file_type = _publish_file_type(context)
    platform = str(getattr(context, "platform", "") or "")

    if file_type == "image":
        image_paths = _split_image_paths(file_path)
        if not image_paths:
            return "未指定发布图片路径"

        missing = _missing_message(image_paths)
        if missing:
            return missing

        for image_path in image_paths:
            if not media_validator.validate_format(image_path, "image", platform):
                return f"图片格式不支持: {os.path.basename(image_path)}"
            if not media_validator.validate_size(image_path, "image", platform):
                return f"图片大小超出限制: {os.path.basename(image_path)}"
        return None

    if not Path(file_path).exists():
        return f"文件不存在: {file_path}"
    if not media_validator.validate_format(file_path, "video", platform):
        return f"文件格式不支持: {file_path}"
    if not media_validator.validate_size(file_path, "video", platform):
        return f"文件大小超出限制: {file_path}"
    return None
