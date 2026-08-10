"""Font loading, and the multiplier that adapts configured text sizes.

A ``text_size`` in widgets.yaml is a pixel count, so ``graphics.text-scale``
multiplies it to suit screens of different resolutions. Sizes a widget derives
from its own cell are already in this screen's pixels and must not be scaled,
so callers apply :func:`scale_text_size` themselves rather than the font cache
doing it for them.
"""

from __future__ import annotations

from functools import lru_cache

import pygame

_text_scale = 1.0


def set_text_scale(scale: float) -> None:
    """Set the multiplier applied to configured text sizes."""
    global _text_scale
    _text_scale = float(scale)


def get_text_scale() -> float:
    return _text_scale


def scale_text_size(size: int) -> int:
    return max(1, round(size * _text_scale))


class FontCache:
    @lru_cache(maxsize=32)
    def get_font(self, name, size):
        return pygame.font.Font(name, size)
