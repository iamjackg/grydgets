"""Shared background painting for widgets that accept ``background_color``.

Three widgets now paint the same square-or-rounded backdrop (``text`` and its
wrappers, ``grid`` cells, ``empty``). Keeping it in one function means a
rounded panel and a square one at the same colour agree pixel-for-pixel on
alpha, which matters because these are composited on top of each other.
"""

from __future__ import annotations

import pygame

from grydgets.colors import Color


def paint_background(
    surface: pygame.Surface,
    color: Color | None,
    size: tuple[int, int],
    corner_radius: int = 0,
) -> None:
    """Fill ``surface`` with ``color``, rounding the corners if asked.

    A ``color`` of ``None`` leaves the surface untouched, so callers can pass
    an unset parameter straight through.
    """
    if color is None:
        return

    rect = pygame.Rect((0, 0), size)
    if corner_radius:
        pygame.draw.rect(surface, color, rect, border_radius=corner_radius)
    else:
        surface.fill(color, rect)
