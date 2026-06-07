import os
import threading

from loguru import logger as log
from src.backend.PluginManager.ActionBase import ActionBase


class TailscaleActionBase(ActionBase):
    """Shared rendering, mutation, and error handling for Tailscale actions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------ #
    # Status / rendering helpers
    # ------------------------------------------------------------------ #
    def get_status(self, max_age: float = 2.0):
        return self.plugin_base.get_status(max_age)

    def set_icon(self, name: str, size: float = 0.75):
        path = os.path.join(self.plugin_base.PATH, "assets", name)
        self.set_media(media_path=path, size=size)

    def safe_set_background(self, color):
        # set_background_color raises AttributeError on some 1.5.0-beta builds.
        try:
            self.set_background_color(color=color)
        except AttributeError:
            pass

    def render(self):
        """Read fresh-ish status and update the button. Overridden per action."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Mutations
    # ------------------------------------------------------------------ #
    def do_mutation(self, fn):
        """Run a blocking backend mutation off the UI thread.

        `tailscale up`/`switch` can block for seconds (handshake, browser
        re-auth), so never call them directly from on_key_down. After the
        command finishes we invalidate the shared status cache and re-render so
        the button reflects the new state immediately.
        """
        def worker():
            ok = False
            try:
                ok = fn()
            except Exception as e:
                log.exception("[tailscale] do_mutation raised: {}", e)
            finally:
                self.plugin_base.invalidate_status()
                try:
                    self.render()
                except Exception:
                    pass
                if not ok:
                    self.show_error(2)

        threading.Thread(target=worker, daemon=True).start()
