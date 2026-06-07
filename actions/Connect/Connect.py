from ..base.TailscaleActionBase import TailscaleActionBase
from ...backend import tailscale_backend as ts


class Connect(TailscaleActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = False

    def on_ready(self):
        self.render()

    def on_tick(self):
        self.render()

    def on_key_down(self):
        self.do_mutation(self.plugin_base.backend.up)

    def render(self):
        status = self.get_status()
        if status is None:
            self.show_error()
            return
        self.hide_error()
        if ts.is_connected(status):
            self.set_icon("connected.png")
            self.safe_set_background([0, 150, 60, 255])
        else:
            self.set_icon("disconnected.png")
            self.safe_set_background([0, 0, 0, 0])
