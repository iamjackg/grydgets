"""Fonts, and the one place a configured text size becomes a pixel height.

A ``text_size`` in widgets.yaml is a number of pixels, so the same value is
physically smaller on a denser screen: 50 that reads well on a 1366x768 panel
is cramped on a 1080p one of the same physical size. ``graphics.text-scale``
in conf.yaml multiplies every text size that was written down, so one
widgets.yaml can serve both machines without a second copy of the file or a
per-device theme.

Only sizes that were written down are scaled. A widget with no ``text_size``
takes its size from the height of its own cell, which already grew with the
resolution -- multiplying that too would push the text out of the cell.
"""

from __future__ import annotations

from functools import lru_cache

import pygame

_text_scale = 1.0


def set_text_scale(scale: float) -> None:
    """Set the multiplier applied to configured text sizes.

    Called once at startup and again on each config reload, before anything
    renders. Widgets read the scale while rendering rather than storing a
    scaled size, so a reload that changes it takes effect on the next frame.
    """
    global _text_scale
    _text_scale = float(scale)


def get_text_scale() -> float:
    return _text_scale


def scale_text_size(size: int) -> int:
    """A configured text size, in the pixels this screen should draw it at."""
    return max(1, round(size * _text_scale))


class FontCache:
    @lru_cache(maxsize=32)
    def get_font(self, name, size):
        return pygame.font.Font(name, size)
