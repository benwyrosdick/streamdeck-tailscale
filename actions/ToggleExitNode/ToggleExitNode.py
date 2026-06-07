import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from ..base.TailscaleActionBase import TailscaleActionBase
from ...backend import tailscale_backend as ts


class ToggleExitNode(TailscaleActionBase):
    """Toggle a per-button configured exit node on and off."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = True
        # Parallel list of exit-node values matching the combo model rows.
        self._node_values = []

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

        settings = self.get_settings()
        configured = settings.get("exit_node")
        label = settings.get("exit_node_label")
        active = ts.active_exit_node(status)

        is_on = bool(active) and configured and self._matches(active, configured)
        if is_on:
            self.set_icon("exit_node_on.png")
            self.safe_set_background([0, 90, 200, 255])
            self.set_bottom_label((label or active.get("name", ""))[:12], font_size=12)
        else:
            self.set_icon("exit_node_off.png")
            self.safe_set_background([0, 0, 0, 0])
            self.set_bottom_label((label or "")[:12], font_size=12)

    def _matches(self, active_node, configured_value) -> bool:
        return configured_value in (active_node.get("dns"), active_node.get("ip"), active_node.get("name"))

    def on_key_down(self):
        settings = self.get_settings()
        configured = settings.get("exit_node")
        if not configured:
            self.show_error(2)
            return

        active = ts.active_exit_node(self.get_status())
        if active and self._matches(active, configured):
            self.do_mutation(self.plugin_base.backend.clear_exit_node)
        else:
            self.do_mutation(lambda: self.plugin_base.backend.set_exit_node(configured))

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
        self._node_values = []
        while self.node_model.get_n_items() > 0:
            self.node_model.remove(0)

        candidates = self.plugin_base.backend.list_exit_node_candidates(self.get_status())
        if not candidates:
            self.node_model.append(self.plugin_base.lm.get("actions.toggle-exit-node.none"))
            self.connect_signals()
            return

        for c in candidates:
            # Use the Tailscale IP as the --exit-node value (most robust,
            # unambiguously documented); show the friendly machine name.
            value = c["ip"] or c["dns"] or c["name"]
            self._node_values.append({"value": value, "label": c["name"]})
            self.node_model.append(c["name"] or value)

        self.connect_signals()

    def load_configs(self):
        self.disconnect_signals()
        settings = self.get_settings()
        configured = settings.get("exit_node")
        index = next((i for i, n in enumerate(self._node_values) if n["value"] == configured), None)
        if index is not None:
            self.node_row.set_selected(index)
        else:
            self.node_row.set_selected(Gtk.INVALID_LIST_POSITION)
        self.connect_signals()

    def on_change(self, *args):
        if not self._node_values:
            return
        index = self.node_row.get_selected()
        if not (0 <= index < len(self._node_values)):
            return
        settings = self.get_settings()
        settings["exit_node"] = self._node_values[index]["value"]
        settings["exit_node_label"] = self._node_values[index]["label"]
        self.set_settings(settings)
