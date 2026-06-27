from loguru import logger as log

from ..base.TailscaleActionBase import TailscaleActionBase
from ...backend import tailscale_backend as ts


class ToggleConnection(TailscaleActionBase):
    """Status-aware on/off button: green when Running, grey when down."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_configuration = False
        # Diagnostics for the "stuck on stale icon" report: track the last
        # rendered state and a tick counter so the log shows whether on_tick
        # keeps firing and what state each render actually computes/draws.
        self._last_rendered = None
        self._tick_count = 0

    def on_ready(self):
        log.info("[tailscale] ToggleConnection on_ready")
        self.render()

    def on_tick(self):
        self._tick_count += 1
        # Low-volume heartbeat (~every 30s) proving the tick loop reaches us.
        if self._tick_count % 30 == 1:
            try:
                present = self.get_is_present()
            except Exception:
                present = "?"
            log.debug(
                "[tailscale] ToggleConnection tick #{} present={} last={}",
                self._tick_count, present, self._last_rendered,
            )
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
            self._note_render("error")
            self.commit_render("error")
            return
        self.hide_error()

        # The account name persists across states; only icon/background change.
        account = (ts.current_account(status) or "")[:12]
        self.set_bottom_label(account, font_size=12)

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
        self._note_render(state)
        # Signature covers icon/background (state) AND the account label, so a
        # change in either forces the panel to repaint past the hash dedup.
        self.commit_render(f"{state}|{account}")

    def _note_render(self, state):
        """Log whenever the rendered state changes, and flag the case where a
        render is requested while the action isn't present (its set_media /
        set_background calls silently no-op, which would strand a stale icon)."""
        if state == self._last_rendered:
            return
        try:
            present = self.get_is_present()
        except Exception:
            present = "?"
        log.info(
            "[tailscale] ToggleConnection render {} -> {} (present={})",
            self._last_rendered, state, present,
        )
        if present is False:
            log.warning(
                "[tailscale] ToggleConnection rendered while NOT present; "
                "icon/background draw will be suppressed -> stale button"
            )
        self._last_rendered = state
