import types
from pathlib import Path

from src.infrastructure.browser.browser_manager import UndetectedBrowserManager
from src.infrastructure.common.path_manager import PathManager


class _FakeProcess:
    def __init__(self, pid, name, cmdline):
        self.info = {"pid": pid, "name": name}
        self._name = name
        self._cmdline = cmdline
        self.terminated = False
        self.killed = False

    def name(self):
        return self._name

    def cmdline(self):
        return self._cmdline

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def _fake_psutil(processes):
    by_pid = {proc.info["pid"]: proc for proc in processes}

    class NoSuchProcess(Exception):
        pass

    class AccessDenied(Exception):
        pass

    class ZombieProcess(Exception):
        pass

    class TimeoutExpired(Exception):
        pass

    return types.SimpleNamespace(
        Process=lambda pid: by_pid[pid],
        process_iter=lambda attrs=None: list(processes),
        NoSuchProcess=NoSuchProcess,
        AccessDenied=AccessDenied,
        ZombieProcess=ZombieProcess,
        TimeoutExpired=TimeoutExpired,
    )


def test_cleanup_all_processes_audits_known_and_scanned_pids(monkeypatch, tmp_path):
    data_root = tmp_path / "app-data"
    data_root.mkdir()
    normalized_root = str(data_root).lower().replace("\\", "/")

    known = _FakeProcess(101, "chrome.exe", [f"--user-data-dir={normalized_root}/profiles/a"])
    scanned = _FakeProcess(202, "chrome.exe", [f"--user-data-dir={normalized_root}/profiles/b"])
    ignored = _FakeProcess(303, "chrome.exe", ["--user-data-dir=c:/other"])
    fake_psutil = _fake_psutil([known, scanned, ignored])

    monkeypatch.setitem(__import__("sys").modules, "psutil", fake_psutil)
    monkeypatch.setattr(PathManager, "get_app_data_dir", lambda: Path(data_root))

    UndetectedBrowserManager._registered_pids = {101}
    UndetectedBrowserManager._last_cleanup_report = {}

    cleaned = UndetectedBrowserManager.cleanup_all_processes()
    report = UndetectedBrowserManager.get_last_cleanup_report()

    assert cleaned == 2
    assert known.terminated is True
    assert scanned.terminated is True
    assert ignored.terminated is False
    assert report["cleaned_count"] == 2
    assert report["known_pids"] == [101]
    assert report["cleaned_pids"] == [101, 202]
    assert report["failed_pids"] == []
    assert report["scanned_processes"] == 3


def test_cleanup_all_processes_respects_excluded_pids(monkeypatch, tmp_path):
    data_root = tmp_path / "app-data"
    data_root.mkdir()
    normalized_root = str(data_root).lower().replace("\\", "/")

    proc = _FakeProcess(101, "chrome.exe", [f"--user-data-dir={normalized_root}/profiles/a"])
    fake_psutil = _fake_psutil([proc])

    monkeypatch.setitem(__import__("sys").modules, "psutil", fake_psutil)
    monkeypatch.setattr(PathManager, "get_app_data_dir", lambda: Path(data_root))

    UndetectedBrowserManager._registered_pids = {101}
    UndetectedBrowserManager._last_cleanup_report = {}

    cleaned = UndetectedBrowserManager.cleanup_all_processes(exclude_pids={101})
    report = UndetectedBrowserManager.get_last_cleanup_report()

    assert cleaned == 0
    assert proc.terminated is False
    assert report["exclude_pids"] == [101]
    assert report["cleaned_pids"] == []
