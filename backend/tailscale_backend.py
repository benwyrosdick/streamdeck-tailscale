"""Thin wrapper around the host `tailscale` CLI.

This module deliberately has NO GTK or StreamController imports so it stays
pure and unit-testable. StreamController runs inside a flatpak sandbox, so the
host binary is reached via `flatpak-spawn --host tailscale ...`. When running
outside a sandbox (e.g. local development) the binary is called directly.

The `python-tailscale` PyPI package is intentionally NOT used: it targets the
Tailscale *cloud* API (needs an API key), whereas we want *local daemon*
control, which is what the CLI provides.

Note on privileges: `status --json` reads work unprivileged, but `up`/`down`/
`set`/`switch` (and `switch --list`) require operator rights. The user enables
this once with `sudo tailscale set --operator=$USER`.
"""

import json
import os
import shutil
import subprocess
from typing import Optional

try:
    from loguru import logger as log
except Exception:  # pragma: no cover - loguru always present inside the app
    import logging
    log = logging.getLogger("tailscale")

# Timeouts (seconds). Status reads are quick; mutations can block on handshake
# or browser re-auth, so they get a generous budget.
STATUS_TIMEOUT = 4
MUTATION_TIMEOUT = 15


class TailscaleBackend:
    def __init__(self):
        # The flatpak sandbox always has /.flatpak-info; the host does not.
        self._sandboxed = os.path.exists("/.flatpak-info")

    # ------------------------------------------------------------------ #
    # Low-level command construction / execution
    # ------------------------------------------------------------------ #
    def _build_cmd(self, args: list) -> list:
        if self._sandboxed:
            # --directory=/ pins a working dir that exists on the host. Without
            # it, flatpak-spawn forwards the caller's cwd (e.g. the app's
            # /app/bin/StreamController), which the host can't chdir into, and
            # every call fails with "Failed to change to directory".
            return ["flatpak-spawn", "--host", "--directory=/", "tailscale", *args]
        return [shutil.which("tailscale") or "tailscale", *args]

    def _run(self, args: list, timeout: int = STATUS_TIMEOUT):
        """Run a tailscale command. Returns (ok, stdout, stderr); never raises."""
        cmd = self._build_cmd(args)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            ok = proc.returncode == 0
            if not ok:
                log.warning("[tailscale] {} -> rc={} err={!r}", args, proc.returncode, (proc.stderr or "").strip()[:200])
            return ok, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            log.error("[tailscale] {} -> TIMEOUT after {}s", cmd, timeout)
            return False, "", "timeout"
        except (FileNotFoundError, OSError) as e:
            log.error("[tailscale] {} -> EXEC FAILED: {}", cmd, e)
            return False, "", str(e)

    # ------------------------------------------------------------------ #
    # Read operations
    # ------------------------------------------------------------------ #
    def get_status(self) -> Optional[dict]:
        """Parsed `tailscale status --json`, or None on any failure."""
        ok, out, _ = self._run(["status", "--json"], timeout=STATUS_TIMEOUT)
        if not ok or not out.strip():
            return None
        try:
            return json.loads(out)
        except (ValueError, TypeError):
            return None

    def list_profiles(self) -> Optional[list]:
        """Parse `tailscale switch --list`.

        Returns a list of {"id", "tailnet", "account", "current"} dicts, or
        None when access is denied (operator not configured) so the UI can
        surface the setup hint instead of an empty picker.
        """
        ok, out, err = self._run(["switch", "--list"], timeout=STATUS_TIMEOUT)
        if not ok:
            return None
        if "access denied" in (err or "").lower():
            return None

        profiles = []
        lines = out.splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip the header row (starts with "ID").
            if stripped.upper().startswith("ID "):
                continue
            current = stripped.endswith("*")
            cleaned = stripped.rstrip("*").strip()
            parts = cleaned.split()
            if not parts:
                continue
            # Columns: ID  TAILNET  ACCOUNT  (last column may be "*")
            profile_id = parts[0]
            tailnet = parts[1] if len(parts) > 1 else ""
            account = parts[2] if len(parts) > 2 else ""
            profiles.append({
                "id": profile_id,
                "tailnet": tailnet,
                "account": account,
                "current": current,
            })
        return profiles

    def list_exit_node_candidates(self, status: Optional[dict] = None) -> list:
        """Exit-node candidates derived from `status` peers.

        `tailscale exit-node list` has no --json flag, but every advertised
        exit node shows up as a peer with ExitNodeOption == True, so we read it
        straight from the status payload (and reuse an already-fetched one when
        provided, to avoid a second subprocess).
        """
        if status is None:
            status = self.get_status()
        if not status:
            return []

        candidates = []
        for peer in (status.get("Peer") or {}).values():
            if not peer.get("ExitNodeOption"):
                continue
            ips = peer.get("TailscaleIPs") or []
            candidates.append({
                "name": _nice_name(peer),
                "dns": (peer.get("DNSName") or "").rstrip("."),
                "ip": ips[0] if ips else "",
                "active": bool(peer.get("ExitNode")),
            })
        candidates.sort(key=lambda c: c["name"].lower())
        return candidates

    # ------------------------------------------------------------------ #
    # Mutating operations (require operator rights)
    # ------------------------------------------------------------------ #
    def up(self) -> bool:
        ok, _, _ = self._run(["up"], timeout=MUTATION_TIMEOUT)
        return ok

    def down(self) -> bool:
        ok, _, _ = self._run(["down"], timeout=MUTATION_TIMEOUT)
        return ok

    def set_exit_node(self, value: str) -> bool:
        ok, _, _ = self._run(["set", f"--exit-node={value}"], timeout=MUTATION_TIMEOUT)
        return ok

    def clear_exit_node(self) -> bool:
        ok, _, _ = self._run(["set", "--exit-node="], timeout=MUTATION_TIMEOUT)
        return ok

    def switch(self, profile: str) -> bool:
        ok, _, _ = self._run(["switch", profile], timeout=MUTATION_TIMEOUT)
        return ok


# ---------------------------------------------------------------------- #
# Pure status interpreters (operate on a `status` dict from get_status())
# ---------------------------------------------------------------------- #
def _nice_name(peer: dict) -> str:
    """The Tailscale machine name (first label of DNSName), as shown in the
    admin console / tsui. Falls back to the OS HostName, which on cloud VMs is
    an unhelpful name like `ip-10-1-11-233`."""
    dns = (peer.get("DNSName") or "").rstrip(".")
    if dns:
        return dns.split(".")[0]
    return peer.get("HostName") or ""


def backend_state(status: Optional[dict]) -> Optional[str]:
    if not status:
        return None
    return status.get("BackendState")


def is_connected(status: Optional[dict]) -> bool:
    return backend_state(status) == "Running"


def current_account(status: Optional[dict]) -> Optional[str]:
    if not status:
        return None
    tailnet = status.get("CurrentTailnet") or {}
    return tailnet.get("Name")


def active_exit_node(status: Optional[dict]) -> Optional[dict]:
    """The peer currently acting as exit node, or None."""
    if not status:
        return None
    for peer in (status.get("Peer") or {}).values():
        if peer.get("ExitNode"):
            ips = peer.get("TailscaleIPs") or []
            return {
                "name": _nice_name(peer),
                "dns": (peer.get("DNSName") or "").rstrip("."),
                "ip": ips[0] if ips else "",
            }
    return None
