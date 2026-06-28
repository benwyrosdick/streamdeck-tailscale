import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk

from ..base.TailscaleActionBase import TailscaleActionBase
from ...backend import tailscale_backend as ts


def _rgba_to_list(rgba: Gdk.RGBA) -> list:
    """Gdk.RGBA (0..1 floats) -> [r, g, b, a] ints (0..255), matching the rest
    of the plugin's color conventions."""
    return [
        round(rgba.red * 255),
        round(rgba.green * 255),
        round(rgba.blue * 255),
        round(rgba.alpha * 255),
    ]


def _list_to_rgba(color: list) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    rgba.red = color[0] / 255
    rgba.green = color[1] / 255
    rgba.blue = color[2] / 255
    rgba.alpha = (color[3] if len(color) > 3 else 255) / 255
    return rgba


# Shown in the color button before the user picks anything. Stored colors only
# get written once the user actually changes a button, so an untouched account
# keeps the deck's default background.
DEFAULT_SWATCH = [60, 60, 60, 255]


class SwitchAccount(TailscaleActionBase):
    """Single button that toggles between two configured Tailscale profiles.

    Each account can be given a background color, shown on the button while
    that account is active so you can tell at a glance which tailnet you're on.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = True
        # Parallel lists matching the combo model rows.
        self._profile_ids = []
        self._profiles = []

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
            self.set_icon("account.png")
            self.show_error()
            self.commit_render("error")
            return
        self.hide_error()

        account = ts.current_account(status)
        if account:
            self.set_bottom_label(account[:12], font_size=12)

        # Tint the button with the active account's color (if one is set), and
        # flip the icon dark when that color is light so it stays legible.
        color = self._color_for_account(account)
        tint = self.icon_tint_for_background(color)
        self.set_icon("account.png", tint=tint)
        self.safe_set_background(color or [0, 0, 0, 0])
        self.commit_render(f"account|{account}|{color}|{tint}")

    def _color_for_account(self, account):
        """The [r,g,b,a] saved for the active account's tailnet, or None.

        `account` is the tailnet name from `current_account()`, which matches
        the TAILNET column of `switch --list` that colors are keyed by — so the
        lookup needs no extra subprocess call."""
        if not account:
            return None
        return (self.get_settings().get("account_colors") or {}).get(account)

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

        # A color swatch per account, attached to its row.
        tooltip = self.plugin_base.lm.get("actions.switch-account.color.tooltip")
        self.color_a_button = self._make_color_button(tooltip)
        self.color_b_button = self._make_color_button(tooltip)
        self.profile_a_row.add_suffix(self.color_a_button)
        self.profile_b_row.add_suffix(self.color_b_button)

        # Slot table drives the generic combo/color handlers below.
        self._slots = (
            ("profile_a", self.profile_a_row, self.color_a_button),
            ("profile_b", self.profile_b_row, self.color_b_button),
        )

        self.connect_signals()
        self.load_models()
        self.load_configs()

        return [self.profile_a_row, self.profile_b_row]

    def _make_color_button(self, tooltip: str) -> Gtk.ColorDialogButton:
        button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        button.set_valign(Gtk.Align.CENTER)
        button.set_tooltip_text(tooltip)
        return button

    def connect_signals(self):
        self.profile_a_row.connect("notify::selected", self.on_change)
        self.profile_b_row.connect("notify::selected", self.on_change)
        self.color_a_button.connect("notify::rgba", self.on_color_a_change)
        self.color_b_button.connect("notify::rgba", self.on_color_b_change)

    def disconnect_signals(self):
        for row in (self.profile_a_row, self.profile_b_row):
            try:
                row.disconnect_by_func(self.on_change)
            except TypeError:
                pass
        for button, handler in (
            (self.color_a_button, self.on_color_a_change),
            (self.color_b_button, self.on_color_b_change),
        ):
            try:
                button.disconnect_by_func(handler)
            except TypeError:
                pass

    def load_models(self):
        self.disconnect_signals()
        self._profile_ids = []
        self._profiles = []
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

        self._profiles = profiles
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
        self._sync_color_button(self.profile_a_row, self.color_a_button)
        self._sync_color_button(self.profile_b_row, self.color_b_button)
        self.connect_signals()

    def _select(self, row, profile_id):
        if profile_id in self._profile_ids:
            row.set_selected(self._profile_ids.index(profile_id))
        else:
            row.set_selected(Gtk.INVALID_LIST_POSITION)

    def _tailnet_for_row(self, row) -> str:
        """Tailnet (the color key) of the profile selected in `row`."""
        index = row.get_selected()
        if 0 <= index < len(self._profiles):
            p = self._profiles[index]
            return p.get("tailnet") or p.get("account") or ""
        return ""

    def _sync_color_button(self, row, button):
        """Show the stored color for the row's selected account (or the default
        swatch). Caller is responsible for having signals disconnected."""
        tailnet = self._tailnet_for_row(row)
        stored = (self.get_settings().get("account_colors") or {}).get(tailnet)
        button.set_rgba(_list_to_rgba(stored or DEFAULT_SWATCH))

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

        # Reflect the newly-selected account's saved color without retriggering
        # the color handlers.
        self.disconnect_signals()
        self._sync_color_button(self.profile_a_row, self.color_a_button)
        self._sync_color_button(self.profile_b_row, self.color_b_button)
        self.connect_signals()

    def on_color_a_change(self, *args):
        self._store_color(self.profile_a_row, self.color_a_button)

    def on_color_b_change(self, *args):
        self._store_color(self.profile_b_row, self.color_b_button)

    def _store_color(self, row, button):
        tailnet = self._tailnet_for_row(row)
        if not tailnet:
            return
        settings = self.get_settings()
        colors = settings.get("account_colors") or {}
        colors[tailnet] = _rgba_to_list(button.get_rgba())
        settings["account_colors"] = colors
        self.set_settings(settings)
