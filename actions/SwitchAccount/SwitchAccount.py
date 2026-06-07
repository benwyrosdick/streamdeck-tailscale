import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from ..base.TailscaleActionBase import TailscaleActionBase
from ...backend import tailscale_backend as ts


class SwitchAccount(TailscaleActionBase):
    """Single button that toggles between two configured Tailscale profiles."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = True
        # Parallel list of profile ids matching the combo model rows.
        self._profile_ids = []

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def on_ready(self):
        self.render()

    def on_tick(self):
        self.render()

    def render(self):
        status = self.get_status()
        self.set_icon("account.png")
        if status is None:
            self.show_error()
            return
        self.hide_error()
        account = ts.current_account(status)
        if account:
            self.set_bottom_label(account[:12], font_size=12)

    def on_key_down(self):
        settings = self.get_settings()
        profile_a = settings.get("profile_a")
        profile_b = settings.get("profile_b")
        if not profile_a or not profile_b:
            self.show_error(2)
            return

        # Figure out which profile is current; switch to the other one.
        target = profile_a
        profiles = self.plugin_base.backend.list_profiles()
        if profiles:
            current_id = next((p["id"] for p in profiles if p["current"]), None)
            if current_id == profile_a:
                target = profile_b
            elif current_id == profile_b:
                target = profile_a

        self.do_mutation(lambda: self.plugin_base.backend.switch(target))

    # ------------------------------------------------------------------ #
    # Configuration UI
    # ------------------------------------------------------------------ #
    def get_config_rows(self) -> list:
        self.profile_a_model = Gtk.StringList()
        self.profile_b_model = Gtk.StringList()

        self.profile_a_row = Adw.ComboRow(
            model=self.profile_a_model,
            title=self.plugin_base.lm.get("actions.switch-account.profile-a.label"),
        )
        self.profile_b_row = Adw.ComboRow(
            model=self.profile_b_model,
            title=self.plugin_base.lm.get("actions.switch-account.profile-b.label"),
        )

        self.connect_signals()
        self.load_models()
        self.load_configs()

        return [self.profile_a_row, self.profile_b_row]

    def connect_signals(self):
        self.profile_a_row.connect("notify::selected", self.on_change)
        self.profile_b_row.connect("notify::selected", self.on_change)

    def disconnect_signals(self):
        for row in (self.profile_a_row, self.profile_b_row):
            try:
                row.disconnect_by_func(self.on_change)
            except TypeError:
                pass

    def load_models(self):
        self.disconnect_signals()
        self._profile_ids = []
        for model in (self.profile_a_model, self.profile_b_model):
            while model.get_n_items() > 0:
                model.remove(0)

        profiles = self.plugin_base.backend.list_profiles()
        if profiles is None:
            # Operator not configured -> surface the one-time setup command.
            hint = self.plugin_base.lm.get("actions.switch-account.needs-operator")
            self.profile_a_model.append(hint)
            self.profile_b_model.append(hint)
            self.connect_signals()
            return

        for p in profiles:
            self._profile_ids.append(p["id"])
            label = p["account"] or p["tailnet"] or p["id"]
            self.profile_a_model.append(label)
            self.profile_b_model.append(label)

        self.connect_signals()

    def load_configs(self):
        self.disconnect_signals()
        settings = self.get_settings()
        self._select(self.profile_a_row, settings.get("profile_a"))
        self._select(self.profile_b_row, settings.get("profile_b"))
        self.connect_signals()

    def _select(self, row, profile_id):
        if profile_id in self._profile_ids:
            row.set_selected(self._profile_ids.index(profile_id))
        else:
            row.set_selected(Gtk.INVALID_LIST_POSITION)

    def on_change(self, *args):
        if not self._profile_ids:
            return
        settings = self.get_settings()
        a_index = self.profile_a_row.get_selected()
        b_index = self.profile_b_row.get_selected()
        if 0 <= a_index < len(self._profile_ids):
            settings["profile_a"] = self._profile_ids[a_index]
        if 0 <= b_index < len(self._profile_ids):
            settings["profile_b"] = self._profile_ids[b_index]
        self.set_settings(settings)
