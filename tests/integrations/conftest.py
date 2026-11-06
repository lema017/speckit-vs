"""Shared test helpers for integration tests."""

import pytest

from specify_cli.integrations import get_integration
from specify_cli.integrations.base import MarkdownIntegration


def native_event_files(key: str) -> list[str]:
    """What an integration with native events adds for its default progress hook."""
    integration = get_integration(key)
    if integration is None or not integration.supports_events():
        return []
    files = [".specify/events.py", integration.events_config_file]
    if key == "opencode":
        files.append(".opencode/plugin/speckit-events.ts")
    return files


@pytest.fixture(autouse=True)
def _core_init_only(monkeypatch: pytest.MonkeyPatch):
    """These tests pin what an integration installs. The fork's default extension has its own, in test_command_init.py."""
    monkeypatch.setattr("specify_cli.command_init.DEFAULT_EXTENSIONS", ())


def _redirect_home(monkeypatch: pytest.MonkeyPatch, home) -> None:
    """Point HOME/USERPROFILE/XDG env vars at an isolated *home* directory."""
    for path in (home, home / ".cache", home / ".config", home / ".local" / "share"):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))


@pytest.fixture(scope="session", autouse=True)
def _isolate_integration_home_session(tmp_path_factory):
    """Isolate the user home for setup that runs outside a test function.

    The per-test fixture below re-points HOME for each test, but function-scoped
    fixtures do not apply to module-/session-scoped fixtures. Some of those (e.g.
    the ``status_*_template`` fixtures in ``test_integration_subcommand.py``) run
    ``specify init`` during setup, before any per-test isolation takes effect.
    A standalone ``MonkeyPatch`` gives them an isolated home too.
    """
    monkeypatch = pytest.MonkeyPatch()
    _redirect_home(monkeypatch, tmp_path_factory.mktemp("session-home"))
    yield
    monkeypatch.undo()


@pytest.fixture(autouse=True)
def _isolate_integration_home(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Keep integration tests from reading or writing the real user home."""
    _redirect_home(monkeypatch, tmp_path / "home")


class StubIntegration(MarkdownIntegration):
    """Minimal concrete integration for testing."""

    key = "stub"
    config = {
        "name": "Stub Agent",
        "folder": ".stub/",
        "commands_subdir": "commands",
        "install_url": None,
        "requires_cli": False,
    }
    registrar_config = {
        "dir": ".stub/commands",
        "format": "markdown",
        "args": "$ARGUMENTS",
        "extension": ".md",
    }
