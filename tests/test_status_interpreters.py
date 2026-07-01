"""Unit tests for the pure status interpreters in backend.tailscale_backend.

These operate on a plain `tailscale status --json` dict and touch no
subprocess, network, or GTK — safe to run anywhere.
"""
from backend.tailscale_backend import (
    TailscaleBackend,
    active_exit_node,
    backend_state,
    current_account,
    is_connected,
    _nice_name,
)


def list_exit_node_candidates(status):
    """Helper: the candidate list is a TailscaleBackend method, but with a
    status passed in it never touches a subprocess."""
    return TailscaleBackend().list_exit_node_candidates(status)


def sample_status():
    return {
        "BackendState": "Running",
        "CurrentTailnet": {"Name": "example.com"},
        "Peer": {
            "keyA": {
                "DNSName": "node-a.example.ts.net.",
                "HostName": "hosta",
                "TailscaleIPs": ["100.64.0.1"],
                "ExitNodeOption": True,
                "ExitNode": False,
            },
            "keyB": {
                "DNSName": "node-b.example.ts.net.",
                "HostName": "hostb",
                "TailscaleIPs": ["100.64.0.2"],
                "ExitNodeOption": True,
                "ExitNode": True,  # currently active exit node
            },
            "keyC": {
                "DNSName": "plain.example.ts.net.",
                "HostName": "hostc",
                "TailscaleIPs": ["100.64.0.3"],
                "ExitNodeOption": False,
                "ExitNode": False,
            },
        },
    }


# --- backend_state / is_connected ---------------------------------------- #

def test_backend_state_reads_field():
    assert backend_state(sample_status()) == "Running"


def test_backend_state_none_on_empty():
    assert backend_state(None) is None
    assert backend_state({}) is None


def test_is_connected_true_when_running():
    assert is_connected(sample_status()) is True


def test_is_connected_false_when_stopped():
    assert is_connected({"BackendState": "Stopped"}) is False
    assert is_connected(None) is False


# --- current_account ----------------------------------------------------- #

def test_current_account():
    assert current_account(sample_status()) == "example.com"


def test_current_account_none_when_missing():
    assert current_account(None) is None
    assert current_account({}) is None


# --- _nice_name ---------------------------------------------------------- #

def test_nice_name_uses_first_dns_label():
    peer = {"DNSName": "node-a.example.ts.net.", "HostName": "hosta"}
    assert _nice_name(peer) == "node-a"


def test_nice_name_falls_back_to_hostname():
    peer = {"DNSName": "", "HostName": "ip-10-1-11-233"}
    assert _nice_name(peer) == "ip-10-1-11-233"


# --- active_exit_node ---------------------------------------------------- #

def test_active_exit_node_returns_the_active_peer():
    node = active_exit_node(sample_status())
    assert node is not None
    assert node["name"] == "node-b"
    assert node["ip"] == "100.64.0.2"
    assert node["dns"] == "node-b.example.ts.net"


def test_active_exit_node_none_when_no_active():
    status = sample_status()
    for peer in status["Peer"].values():
        peer["ExitNode"] = False
    assert active_exit_node(status) is None


# --- list_exit_node_candidates ------------------------------------------- #

def test_list_exit_node_candidates_only_advertised_sorted():
    candidates = list_exit_node_candidates(sample_status())
    names = [c["name"] for c in candidates]
    assert names == ["node-a", "node-b"]  # sorted, plain peer excluded


def test_list_exit_node_candidates_marks_active():
    candidates = list_exit_node_candidates(sample_status())
    by_name = {c["name"]: c for c in candidates}
    assert by_name["node-b"]["active"] is True
    assert by_name["node-a"]["active"] is False


def test_list_exit_node_candidates_empty_without_status():
    assert list_exit_node_candidates({}) == []
