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

    def commit_render(self, signature):
        """Guarantee the latest render reaches the physical key.

        StreamController skips a repaint whenever the composed image's hash
        matches the previous one (DeckController.ControllerKey.update). It
        advances that stored hash *before* the async paint task is confirmed,
        so when a paint is dropped or superseded -- which happens during page
        reloads and status transitions -- the key is stranded on a stale frame
        and every subsequent render is deduped away. That is the "stuck until I
        press the button" bug (a key press changes the image via the press
        highlight, which is the only thing that breaks the dedup).

        Call this at the end of render() with a signature describing everything
        visible (icon + background + label). When it changes we force one
        repaint that bypasses the hash, so the new frame always lands. On
        unchanged renders we do nothing, preserving the dedup's efficiency.
        """
        if signature == getattr(self, "_last_render_sig", None):
            return
        self._last_render_sig = signature

        inp = self.get_input()
        if inp is None:
            return
        try:
            inp.update(force=True)
        except TypeError:
            # Dials/touchscreens have an update() without a `force` parameter.
            try:
                inp.update()
            except Exception:
                pass
        except Exception:
            # Never let a redraw failure escape render().
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
                # Force a fresh read (bypassing the cache and any in-flight
                # periodic fetch) so the button reflects the new state right
                # away instead of waiting for the next tick.
                self.plugin_base.invalidate_status()
                self.plugin_base.get_status(force=True)
                try:
                    self.render()
                except Exception:
                    pass
                if not ok:
                    self.show_error(2)

        threading.Thread(target=worker, daemon=True).start()
