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
            github_repo="https://github.com/vesyl/streamdeck-tailscale",
            plugin_version="1.0.0",
            app_version="1.5.0-beta.14",
        )

    # ------------------------------------------------------------------ #
    # Shared cached status
    # ------------------------------------------------------------------ #
    def get_status(self, max_age_seconds: float = 2.0):
        """Return a recent `tailscale status --json` dict (or None on failure).

        Re-fetches only when the cached value is older than max_age_seconds.
        """
        now = time.monotonic()
        with self._status_lock:
            if self._status_cache is not None and (now - self._status_cache_ts) < max_age_seconds:
                return self._status_cache
            status = self.backend.get_status()
            if status is not None:
                self._status_cache = status
                self._status_cache_ts = now
            return status

    def invalidate_status(self):
        """Force the next get_status() to re-fetch (call after a mutation)."""
        with self._status_lock:
            self._status_cache_ts = 0.0
