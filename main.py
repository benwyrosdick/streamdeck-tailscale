# Import StreamController modules
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.DeckManagement.InputIdentifier import Input

import time
import threading

# Relative imports anchor every module to this plugin's package. Absolute
# top-level names like `actions`/`backend` would collide with the identically
# named packages other installed plugins register in sys.modules.
from .backend.tailscale_backend import TailscaleBackend

from .actions.Connect.Connect import Connect
from .actions.Disconnect.Disconnect import Disconnect
from .actions.ToggleConnection.ToggleConnection import ToggleConnection
from .actions.SwitchAccount.SwitchAccount import SwitchAccount
from .actions.ToggleExitNode.ToggleExitNode import ToggleExitNode


class TailscalePlugin(PluginBase):
    def __init__(self):
        super().__init__()

        self.lm = self.locale_manager
        self.backend = TailscaleBackend()

        # Shared status cache. Every action polls through get_status(), so the
        # daemon is queried at most once per cache window no matter how many
        # buttons exist or how often on_tick fires.
        self._status_cache = None
        self._status_cache_ts = 0.0
        self._status_lock = threading.Lock()
        # True while a background fetch is mid-flight. Lets concurrent callers
        # reuse the cached value instead of queueing behind the subprocess.
        self._status_fetching = False

        # Register actions
        self.connect_holder = ActionHolder(
            plugin_base=self,
            action_base=Connect,
            action_id_suffix="Connect",
            action_name=self.lm.get("actions.connect.name"),
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.SUPPORTED,
                Input.Touchscreen: ActionInputSupport.UNTESTED,
            },
        )
        self.add_action_holder(self.connect_holder)

        self.disconnect_holder = ActionHolder(
            plugin_base=self,
            action_base=Disconnect,
            action_id_suffix="Disconnect",
            action_name=self.lm.get("actions.disconnect.name"),
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.SUPPORTED,
                Input.Touchscreen: ActionInputSupport.UNTESTED,
            },
        )
        self.add_action_holder(self.disconnect_holder)

        self.toggle_connection_holder = ActionHolder(
            plugin_base=self,
            action_base=ToggleConnection,
            action_id_suffix="ToggleConnection",
            action_name=self.lm.get("actions.toggle-connection.name"),
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.SUPPORTED,
                Input.Touchscreen: ActionInputSupport.UNTESTED,
            },
        )
        self.add_action_holder(self.toggle_connection_holder)

        self.switch_account_holder = ActionHolder(
            plugin_base=self,
            action_base=SwitchAccount,
            action_id_suffix="SwitchAccount",
            action_name=self.lm.get("actions.switch-account.name"),
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.SUPPORTED,
                Input.Touchscreen: ActionInputSupport.UNTESTED,
            },
        )
        self.add_action_holder(self.switch_account_holder)

        self.toggle_exit_node_holder = ActionHolder(
            plugin_base=self,
            action_base=ToggleExitNode,
            action_id_suffix="ToggleExitNode",
            action_name=self.lm.get("actions.toggle-exit-node.name"),
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.SUPPORTED,
                Input.Touchscreen: ActionInputSupport.UNTESTED,
            },
        )
        self.add_action_holder(self.toggle_exit_node_holder)

        # Register plugin
        self.register(
            plugin_name=self.lm.get("plugin.name"),
            github_repo="https://github.com/benwyrosdick/streamdeck-tailscale",
            plugin_version="1.0.0",
            app_version="1.5.0-beta.14",
        )

    # ------------------------------------------------------------------ #
    # Shared cached status
    # ------------------------------------------------------------------ #
    def get_status(self, max_age_seconds: float = 2.0, force: bool = False):
        """Return a recent `tailscale status --json` dict (or None on failure).

        Re-fetches only when the cached value is older than max_age_seconds.

        The blocking `tailscale status` subprocess runs OUTSIDE the lock so a
        slow/stalled call can never freeze other buttons' renders. A
        single-flight guard means only one periodic fetch runs at a time;
        concurrent callers (every action's on_tick fires its own thread each
        second) get the current cached value immediately instead of piling up
        behind the lock. A transient fetch failure serves the last good value
        rather than flashing an error and stranding a stale icon.

        `force=True` always performs a fresh fetch and bypasses the
        single-flight guard. Mutations (up/down/switch) use it so the button
        reflects the new state the instant the command returns.
        """
        now = time.monotonic()
        if not force:
            with self._status_lock:
                fresh = (
                    self._status_cache is not None
                    and (now - self._status_cache_ts) < max_age_seconds
                )
                if fresh or self._status_fetching:
                    # Cache is fresh, or someone else is already refreshing it:
                    # return what we have (never block on the subprocess).
                    return self._status_cache
                self._status_fetching = True

        status = None
        try:
            status = self.backend.get_status()
        finally:
            with self._status_lock:
                if not force:
                    self._status_fetching = False
                if status is not None:
                    self._status_cache = status
                    self._status_cache_ts = time.monotonic()
                else:
                    # Transient failure: keep serving the last good value.
                    status = self._status_cache
        return status

    def invalidate_status(self):
        """Force the next get_status() to re-fetch (call after a mutation)."""
        with self._status_lock:
            self._status_cache_ts = 0.0
