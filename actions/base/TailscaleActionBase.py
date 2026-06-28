import os
import threading

from loguru import logger as log
from PIL import Image
from src.backend.PluginManager.ActionBase import ActionBase

# RGB used when an icon is recolored dark for legibility on a light background.
DARK_ICON_RGB = (30, 30, 30)


class TailscaleActionBase(ActionBase):
    """Shared rendering, mutation, and error handling for Tailscale actions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cache of recolored icons keyed by (path, tint) so we don't reprocess
        # the PNG on every tick.
        self._icon_cache = {}

    # ------------------------------------------------------------------ #
    # Status / rendering helpers
    # ------------------------------------------------------------------ #
    def get_status(self, max_age: float = 2.0):
        return self.plugin_base.get_status(max_age)

    def set_icon(self, name: str, size: float = 0.75, tint=None):
        """Draw an asset icon, optionally recolored to a solid `tint` (an
        (r, g, b) tuple). Tinting keeps the PNG's alpha mask, so the icon's
        shape is preserved while its color is replaced — used to render a dark
        icon over light backgrounds."""
        path = os.path.join(self.plugin_base.PATH, "assets", name)
        if tint is None:
            self.set_media(media_path=path, size=size)
            return
        self.set_media(image=self._tinted_icon(path, tint), size=size)

    def _tinted_icon(self, path: str, tint) -> "Image.Image":
        key = (path, tuple(tint))
        cached = self._icon_cache.get(key)
        if cached is not None:
            return cached
        base = Image.open(path).convert("RGBA")
        solid = Image.new("RGBA", base.size, (tint[0], tint[1], tint[2], 0))
        solid.putalpha(base.getchannel("A"))
        self._icon_cache[key] = solid
        return solid

    def icon_tint_for_background(self, color):
        """Return DARK_ICON_RGB when `color` is a light, mostly-opaque
        background (so the otherwise-light icon stays legible); else None.

        Transparent/low-alpha colors fall through to None because the deck's
        own (dark) background shows behind them.
        """
        if not color:
            return None
        r, g, b = color[0], color[1], color[2]
        alpha = color[3] if len(color) > 3 else 255
        if alpha < 128:
            return None
        # Perceptual luminance (Rec. 601). ~150/255 is a sensible light/dark cut.
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return DARK_ICON_RGB if luminance > 150 else None

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
