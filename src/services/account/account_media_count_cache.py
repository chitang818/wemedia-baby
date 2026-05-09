"""
账号媒体库数量缓存（全局复用）

用途：
- 账号管理页会异步统计每个账号的「视频库/图文库」数量；
- 其它弹窗（如「选择发布对象」）只读这份缓存并订阅更新信号，避免重复扫描磁盘造轮子。
"""

from __future__ import annotations

from typing import Dict, Tuple, Iterable, Optional

from PySide6.QtCore import QObject, Signal


class AccountMediaCountCache(QObject):
    """全局账号素材数量缓存（单例）。"""

    # payload: {account_id: (video_count, image_folder_count)}
    # 用 object（PyObject）避免 Shiboken 尝试拷贝转换 dict 到 C++ 类型导致报错
    countsUpdated = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._counts: Dict[int, Tuple[int, int]] = {}

    def set_counts(self, mapping: Dict[int, Tuple[int, int]]) -> None:
        if not isinstance(mapping, dict) or not mapping:
            return
        changed: Dict[int, Tuple[int, int]] = {}
        for k, v in mapping.items():
            try:
                aid = int(k)
                vc, ic = int(v[0]), int(v[1])
            except Exception:
                continue
            old = self._counts.get(aid)
            if old != (vc, ic):
                self._counts[aid] = (vc, ic)
                changed[aid] = (vc, ic)
        if changed:
            self.countsUpdated.emit(changed)

    def get(self, account_id: int) -> Optional[Tuple[int, int]]:
        try:
            aid = int(account_id)
        except Exception:
            return None
        return self._counts.get(aid)

    def get_many(self, account_ids: Iterable[int]) -> Dict[int, Tuple[int, int]]:
        out: Dict[int, Tuple[int, int]] = {}
        for aid in account_ids:
            try:
                a = int(aid)
            except Exception:
                continue
            if a in self._counts:
                out[a] = self._counts[a]
        return out


_INSTANCE: Optional[AccountMediaCountCache] = None


def get_account_media_count_cache() -> AccountMediaCountCache:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = AccountMediaCountCache()
    return _INSTANCE

