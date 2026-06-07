import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from ..base.TailscaleActionBase import TailscaleActionBase
from ...backend import tailscale_backend as ts

# Sentinel stored when the user wants Tailscale to auto-pick the exit node.
AUTO = "auto"
AUTO_EXIT_NODE = "auto:any"


class ToggleExitNode(TailscaleActionBase):
    """Toggle an exit node on/off.

    The chosen node is remembered per network (tailnet), because a node from
    one account doesn't exist on another. When the node picked for the current
    network isn't available — e.g. right after switching accounts — the button
    falls back to Tailscale's automatic exit-node selection (auto:any) so it
    never fails.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = True
        # Combo options in display order; index 0 is always "Automatic".
        # Each entry: {"value": <ip|AUTO>, "label": <str>}.
        self._options = []

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def on_ready(self):
        self.render()

    def on_tick(self):
        self.render()

    def render(self):
        status = self.get_status()
        if status is None:
            self.show_error()
            return
        self.hide_error()

        active = ts.active_exit_node(status)
        if active:
            self.set_icon("exit_node_on.png")
            self.safe_set_background([0, 90, 200, 255])
            self.set_bottom_label((active.get("name") or "")[:12], font_size=12)
        else:
            self.set_icon("exit_node_off.png")
            self.safe_set_background([0, 0, 0, 0])
            self.set_bottom_label(self._configured_label(status)[:12], font_size=12)

    def on_key_down(self):
        status = self.get_status()
        if status is None:
            self.show_error(2)
            return

        # Pressing always turns off whatever exit node is currently active.
        if ts.active_exit_node(status):
            self.do_mutation(self.plugin_base.backend.clear_exit_node)
            return

        target = self._target_for_network(status)
        self.do_mutation(lambda: self.plugin_base.backend.set_exit_node(target))

    # ------------------------------------------------------------------ #
    # Per-network choice resolution
    # ------------------------------------------------------------------ #
    def _network(self, status) -> str:
        return ts.current_account(status) or ""

    def _chosen_for_network(self, status):
        """The {"value","label"} saved for the current network, or None."""
        nbn = self.get_settings().get("nodes_by_network") or {}
        return nbn.get(self._network(status))

    def _target_for_network(self, status) -> str:
        """The --exit-node value to apply on the current network."""
        chosen = self._chosen_for_network(status)
        value = chosen.get("value") if chosen else None
        if value and value != AUTO:
            # Only honour the saved node if it still exists on this network.
            candidates = self.plugin_base.backend.list_exit_node_candidates(status)
            if any(c["ip"] == value for c in candidates):
                return value
        return AUTO_EXIT_NODE

    def _configured_label(self, status) -> str:
        chosen = self._chosen_for_network(status)
        if chosen and chosen.get("value") not in (None, AUTO):
            return chosen.get("label") or ""
        return self.plugin_base.lm.get("actions.toggle-exit-node.auto-short")

    # ------------------------------------------------------------------ #
    # Configuration UI
    # ------------------------------------------------------------------ #
    def get_config_rows(self) -> list:
        self.node_model = Gtk.StringList()
        self.node_row = Adw.ComboRow(
            model=self.node_model,
            title=self.plugin_base.lm.get("actions.toggle-exit-node.node.label"),
            subtitle=self.plugin_base.lm.get("actions.toggle-exit-node.node.subtitle"),
        )

        self.connect_signals()
        self.load_model()
        self.load_configs()

        return [self.node_row]

    def connect_signals(self):
        self.node_row.connect("notify::selected", self.on_change)

    def disconnect_signals(self):
        try:
            self.node_row.disconnect_by_func(self.on_change)
        except TypeError:
            pass

    def load_model(self):
        self.disconnect_signals()
        self._options = []
        while self.node_model.get_n_items() > 0:
            self.node_model.remove(0)

        # First option: let Tailscale pick automatically.
        auto_label = self.plugin_base.lm.get("actions.toggle-exit-node.auto")
        self._options.append({"value": AUTO, "label": auto_label})
        self.node_model.append(auto_label)

        for c in self.plugin_base.backend.list_exit_node_candidates(self.get_status()):
            self._options.append({"value": c["ip"], "label": c["name"]})
            self.node_model.append(c["name"] or c["ip"])

        self.connect_signals()

    def load_configs(self):
        self.disconnect_signals()
        chosen = self._chosen_for_network(self.get_status())
        target = chosen.get("value") if chosen else AUTO
        index = next((i for i, o in enumerate(self._options) if o["value"] == target), 0)
        self.node_row.set_selected(index)
        self.connect_signals()

    def on_change(self, *args):
        if not self._options:
            return
        index = self.node_row.get_selected()
        if not (0 <= index < len(self._options)):
            return
        opt = self._options[index]

        settings = self.get_settings()
        nbn = settings.get("nodes_by_network") or {}
        nbn[self._network(self.get_status())] = {"value": opt["value"], "label": opt["label"]}
        settings["nodes_by_network"] = nbn
        self.set_settings(settings)
