"""Unit tests for the subprocess seam of TailscaleBackend.

The real subprocess is never invoked: `_run` is monkeypatched, so these tests
need no network, no tailscale CLI, and no flatpak sandbox. We verify command
construction (`_build_cmd`) and the parsing/return behavior layered on top of
`_run`.
"""
import json

import pytest

from backend.tailscale_backend import TailscaleBackend


class FakeRun:
    """Records the args passed to _run and returns a canned (ok, out, err)."""

    def __init__(self, ok=True, out="", err=""):
        self.ok, self.out, self.err = ok, out, err
        self.calls = []

    def __call__(self, args, timeout=None):
        self.calls.append((list(args), timeout))
        return self.ok, self.out, self.err


@pytest.fixture
def backend():
    return TailscaleBackend()


# --- _build_cmd ---------------------------------------------------------- #

def test_build_cmd_sandboxed_uses_flatpak_spawn(backend):
    backend._sandboxed = True
    cmd = backend._build_cmd(["status", "--json"])
    assert cmd[:4] == ["flatpak-spawn", "--host", "--directory=/", "tailscale"]
    assert cmd[4:] == ["status", "--json"]


def test_build_cmd_host_calls_tailscale_directly(backend):
    backend._sandboxed = False
    cmd = backend._build_cmd(["up"])
    assert cmd[-1] == "up"
    assert "flatpak-spawn" not in cmd
    assert cmd[0].endswith("tailscale")


# --- get_status ---------------------------------------------------------- #

def test_get_status_parses_json(backend):
    payload = {"BackendState": "Running"}
    backend._run = FakeRun(ok=True, out=json.dumps(payload))
    assert backend.get_status() == payload


def test_get_status_none_on_failure(backend):
    backend._run = FakeRun(ok=False, out="", err="boom")
    assert backend.get_status() is None


def test_get_status_none_on_bad_json(backend):
    backend._run = FakeRun(ok=True, out="not json")
    assert backend.get_status() is None


def test_get_status_none_on_empty_output(backend):
    backend._run = FakeRun(ok=True, out="   ")
    assert backend.get_status() is None


# --- list_profiles ------------------------------------------------------- #

PROFILE_OUTPUT = (
    "ID     Tailnet          Account\n"
    "abc123 example.com      alice@example.com\n"
    "def456 other.org        bob@other.org      *\n"
)


def test_list_profiles_parses_rows_and_current(backend):
    backend._run = FakeRun(ok=True, out=PROFILE_OUTPUT)
    profiles = backend.list_profiles()
    assert len(profiles) == 2
    assert profiles[0] == {
        "id": "abc123",
        "tailnet": "example.com",
        "account": "alice@example.com",
        "current": False,
    }
    assert profiles[1]["id"] == "def456"
    assert profiles[1]["current"] is True


def test_list_profiles_none_on_failure(backend):
    backend._run = FakeRun(ok=False, out="", err="")
    assert backend.list_profiles() is None


def test_list_profiles_none_on_access_denied(backend):
    backend._run = FakeRun(ok=True, out="", err="Access denied: operator not set")
    assert backend.list_profiles() is None


# --- mutations ----------------------------------------------------------- #

def test_up_returns_true_and_calls_up(backend):
    fake = FakeRun(ok=True)
    backend._run = fake
    assert backend.up() is True
    assert fake.calls[0][0] == ["up"]


def test_down_returns_false_on_failure(backend):
    backend._run = FakeRun(ok=False)
    assert backend.down() is False


def test_switch_passes_profile_arg(backend):
    fake = FakeRun(ok=True)
    backend._run = fake
    assert backend.switch("abc123") is True
    assert fake.calls[0][0] == ["switch", "abc123"]


def test_set_exit_node_formats_flag(backend):
    fake = FakeRun(ok=True)
    backend._run = fake
    backend.set_exit_node("100.64.0.2")
    assert fake.calls[0][0] == ["set", "--exit-node=100.64.0.2"]


def test_clear_exit_node_uses_empty_flag(backend):
    fake = FakeRun(ok=True)
    backend._run = fake
    backend.clear_exit_node()
    assert fake.calls[0][0] == ["set", "--exit-node="]
