from ..base.TailscaleActionBase import TailscaleActionBase
from ...backend import tailscale_backend as ts


class ToggleConnection(TailscaleActionBase):
    """Status-aware on/off button: green when Running, grey when down."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = False

    def on_ready(self):
        self.render()

    def on_tick(self):
        self.render()

    def on_key_down(self):
        status = self.get_status()
        if ts.is_connected(status):
            self.do_mutation(self.plugin_base.backend.down)
        else:
            self.do_mutation(self.plugin_base.backend.up)

    def render(self):
        status = self.get_status()
        if status is None:
            self.show_error()
            self.safe_set_background([120, 120, 120, 255])
            return
        self.hide_error()

        # The account name persists across states; only icon/background change.
        self.set_bottom_label((ts.current_account(status) or "")[:12], font_size=12)

        state = ts.backend_state(status)
        if state == "Running":
            self.set_icon("connected.png")
            self.safe_set_background([0, 150, 60, 255])
        elif state in ("Starting", "NoState"):
            self.set_icon("connecting.png")
            self.safe_set_background([200, 140, 0, 255])
        else:
            self.set_icon("disconnected.png")
            self.safe_set_background([0, 0, 0, 0])  # default deck background
