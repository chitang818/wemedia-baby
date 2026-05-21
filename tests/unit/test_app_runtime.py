import pytest

from src.infrastructure.common import app_runtime


@pytest.mark.asyncio
async def test_run_desktop_runtime_cleans_up_after_success(monkeypatch):
    calls = []

    monkeypatch.setattr(
        app_runtime,
        "inject_52pojie_local_user",
        lambda: calls.append("inject_user"),
    )
    monkeypatch.setattr(
        app_runtime,
        "create_and_show_main_window",
        lambda: "window",
    )
    monkeypatch.setattr(
        app_runtime,
        "schedule_auto_login",
        lambda task_registry: calls.append(("auto_login", task_registry)),
    )
    monkeypatch.setattr(
        app_runtime,
        "schedule_heartbeat",
        lambda task_registry: calls.append(("heartbeat", task_registry)),
    )
    monkeypatch.setattr(
        app_runtime,
        "connect_main_window_activation",
        lambda local_server, window: calls.append(("activation", local_server, window)),
    )
    monkeypatch.setattr(
        app_runtime,
        "schedule_plugin_loading",
        lambda task_registry: calls.append(("plugins", task_registry)),
    )
    monkeypatch.setattr(
        app_runtime,
        "schedule_optional_browser_warmup",
        lambda task_registry: calls.append(("warmup", task_registry)),
    )

    async def wait_for_quit(app):
        calls.append(("wait", app))

    async def cleanup(*, task_registry, loop):
        calls.append(("cleanup", task_registry, loop))

    monkeypatch.setattr(app_runtime, "wait_for_application_quit", wait_for_quit)
    monkeypatch.setattr(app_runtime, "cleanup_application_resources", cleanup)

    result = await app_runtime.run_desktop_runtime(
        app="app",
        local_server="server",
        loop="loop",
        task_registry="registry",
    )

    assert result == 0
    assert calls == [
        "inject_user",
        ("auto_login", "registry"),
        ("heartbeat", "registry"),
        ("activation", "server", "window"),
        ("plugins", "registry"),
        ("warmup", "registry"),
        ("wait", "app"),
        ("cleanup", "registry", "loop"),
    ]


@pytest.mark.asyncio
async def test_run_desktop_runtime_cleans_up_after_startup_failure(monkeypatch):
    calls = []

    def fail_to_create_window():
        calls.append("create_window")
        raise RuntimeError("window failed")

    async def cleanup(*, task_registry, loop):
        calls.append(("cleanup", task_registry, loop))

    monkeypatch.setattr(app_runtime, "inject_52pojie_local_user", lambda: None)
    monkeypatch.setattr(app_runtime, "create_and_show_main_window", fail_to_create_window)
    monkeypatch.setattr(app_runtime, "cleanup_application_resources", cleanup)

    result = await app_runtime.run_desktop_runtime(
        app="app",
        local_server="server",
        loop="loop",
        task_registry="registry",
    )

    assert result == 1
    assert calls == ["create_window", ("cleanup", "registry", "loop")]


def test_connect_main_window_activation_restores_hidden_window(monkeypatch):
    captured = {}
    calls = []

    def fake_connect_activation_handler(local_server, activate):
        captured["local_server"] = local_server
        captured["activate"] = activate

    class Window:
        def __init__(self):
            self.visible = False

        def isVisible(self):
            return self.visible

        def _persist_start_in_tray_next_launch(self, enabled):
            calls.append(("persist_tray", enabled))

        def showNormal(self):
            calls.append("show_normal")
            self.visible = True

        def bring_to_foreground(self):
            calls.append("foreground")

    monkeypatch.setattr(
        app_runtime,
        "connect_activation_handler",
        fake_connect_activation_handler,
    )

    window = Window()
    app_runtime.connect_main_window_activation("server", window)
    captured["activate"]()

    assert captured["local_server"] == "server"
    assert calls == [("persist_tray", False), "show_normal", "foreground"]


def test_schedule_optional_browser_warmup_skips_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_BROWSER_WARMUP_ON_START", raising=False)

    class Registry:
        def create_task(self, *args, **kwargs):
            raise AssertionError("browser warmup should not be scheduled")

    app_runtime.schedule_optional_browser_warmup(Registry())


def test_schedule_optional_browser_warmup_runs_when_enabled(monkeypatch):
    calls = []

    class Registry:
        def create_task(self, coro, *, name, group):
            calls.append((name, group, coro))
            coro.close()

    monkeypatch.setenv("ENABLE_BROWSER_WARMUP_ON_START", "1")

    app_runtime.schedule_optional_browser_warmup(Registry())

    assert [(name, group) for name, group, _ in calls] == [
        ("startup.browser_warmup", "startup")
    ]
