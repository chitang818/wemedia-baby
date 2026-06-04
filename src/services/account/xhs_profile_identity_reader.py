"""Best-effort offline identity extraction from a closed XHS Chrome profile."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class XhsProfileIdentity:
    nickname: Optional[str] = None
    user_id: Optional[str] = None


class XhsProfileIdentityReader:
    """Reads non-cookie identity hints from Chromium local storage files."""

    STORAGE_REL_DIR = Path("Default") / "Local Storage" / "leveldb"
    MAX_FILE_BYTES = 8 * 1024 * 1024
    MAX_TOTAL_BYTES = 32 * 1024 * 1024
    FILE_SUFFIXES = {".log", ".ldb", ".sst"}

    def read_identity(self, user_data_dir: str | Path) -> XhsProfileIdentity:
        storage_dir = Path(user_data_dir) / self.STORAGE_REL_DIR
        if not storage_dir.is_dir():
            return XhsProfileIdentity()

        total = 0
        best_nickname: Optional[str] = None
        best_user_id: Optional[str] = None

        for path in sorted(storage_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.suffix.lower() not in self.FILE_SUFFIXES or not path.is_file():
                continue
            try:
                size = path.stat().st_size
                if size <= 0:
                    continue
                total += min(size, self.MAX_FILE_BYTES)
                if total > self.MAX_TOTAL_BYTES:
                    break
                data = path.read_bytes()[: self.MAX_FILE_BYTES]
            except OSError:
                continue

            for text in self._decode_candidates(data):
                nickname = self._extract_nickname(text)
                if nickname:
                    best_nickname = nickname
                user_id = self._extract_user_id(text)
                if user_id:
                    best_user_id = user_id
                if best_nickname and best_user_id:
                    return XhsProfileIdentity(best_nickname, best_user_id)

        return XhsProfileIdentity(best_nickname, best_user_id)

    def _decode_candidates(self, data: bytes) -> list[str]:
        texts = [
            data.decode("utf-8", errors="ignore"),
            data.decode("utf-16-le", errors="ignore"),
        ]
        normalized: list[str] = []
        for text in texts:
            if not text:
                continue
            normalized.append(text)
            normalized.append(text.replace('\\"', '"'))
        return normalized

    def _extract_nickname(self, text: str) -> Optional[str]:
        for value in self._json_field_values(
            text,
            ("nickname", "nickName", "displayName", "userName", "username", "name"),
        ):
            cleaned = self._clean_nickname(value)
            if cleaned:
                return cleaned
        return None

    def _extract_user_id(self, text: str) -> Optional[str]:
        for value in self._json_field_values(text, ("userId", "user_id", "user_id_creator", "redId")):
            cleaned = str(value or "").strip()
            if re.fullmatch(r"[A-Za-z0-9_-]{4,64}", cleaned):
                return cleaned
        return None

    def _json_field_values(self, text: str, keys: tuple[str, ...]):
        for key in keys:
            pattern = re.compile(
                rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\]){{1,160}})"',
                re.IGNORECASE,
            )
            for match in pattern.finditer(text):
                raw = match.group(1)
                try:
                    yield json.loads(f'"{raw}"')
                except Exception:
                    yield raw

    def _clean_nickname(self, value: object) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        text = text.replace("退出登录", "").strip()
        if not (1 < len(text) <= 40):
            return None
        blocked = ("创作服务平台", "登录", "http://", "https://", "{", "}", "小红书用户_")
        if any(item in text for item in blocked):
            return None
        return text
