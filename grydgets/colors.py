"""Colour parsing for widget parameters.

Every colour a widget accepts goes through :func:`parse_color`, which takes
either the list form that ``widgets.yaml`` has always used (``[255, 136, 0]``)
or a CSS-style string (``"#f80"``, ``"#ff8800"``, ``"#ff8800cc"``, ``"orange"``)
and returns an RGBA 4-tuple.

Parsing lives here rather than in the widget-tree builder because
``WidgetManager.create_widget_tree`` passes YAML keys straight through as
kwargs and has no idea which of them are colours. Two chart parameters
(``bar_colors``, ``bar_color_thresholds``) also nest colours inside a dict and
a list of dicts, which only the widget itself knows how to walk.

Results are always 4-tuples even when the input had no alpha. Widgets compare
old and new colours to decide whether to re-render, so a colour that parsed to
a 3-tuple down one path and a 4-tuple down another would look like a change
every time and force a redraw on hardware that can't spare it.
"""

from __future__ import annotations

from typing import Any, Sequence

import pygame

Color = tuple[int, int, int, int]

# What a widget accepts for a colour parameter, before parsing.
ColorInput = str | Sequence[int]


class ColorError(ValueError):
    """Raised when a colour value can't be parsed."""


def _from_string(value: str) -> Color:
    text = value.strip()

    if text.startswith("#"):
        digits = text[1:]
        # pygame handles #rrggbb and #rrggbbaa but not the 3/4-digit shorthand,
        # so expand that ourselves: #f80 -> #ff8800.
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits)
        if len(digits) not in (6, 8):
            raise ColorError(
                f"{value!r} is not a valid hex colour "
                "(expected #rgb, #rgba, #rrggbb, or #rrggbbaa)"
            )
        try:
            int(digits, 16)
        except ValueError:
            raise ColorError(f"{value!r} contains non-hex digits") from None
        text = "#" + digits

    try:
        parsed = pygame.Color(text)
    except ValueError:
        raise ColorError(
            f"{value!r} is not a recognised colour. Use a hex string like "
            '"#ff8800", a CSS colour name like "orange", or a list such as '
            "[255, 136, 0]"
        ) from None

    return (parsed.r, parsed.g, parsed.b, parsed.a)


def _from_sequence(value: Sequence[Any]) -> Color:
    components = list(value)
    if len(components) not in (3, 4):
        raise ColorError(
            f"{value!r} must have 3 (RGB) or 4 (RGBA) components, "
            f"got {len(components)}"
        )

    parsed = []
    for component in components:
        if isinstance(component, bool) or not isinstance(component, int):
            raise ColorError(f"{value!r} has a non-integer component {component!r}")
        if not 0 <= component <= 255:
            raise ColorError(f"{value!r} has a component outside 0-255: {component}")
        parsed.append(component)

    if len(parsed) == 3:
        parsed.append(255)
    return (parsed[0], parsed[1], parsed[2], parsed[3])


def parse_color(value: Any, field: str | None = None) -> Color:
    """Normalise ``value`` to an RGBA 4-tuple.

    ``field`` names the parameter being parsed and is used to make the error
    message point at the offending line in widgets.yaml.
    """
    try:
        if isinstance(value, str):
            return _from_string(value)
        if isinstance(value, Sequence):
            return _from_sequence(value)
        raise ColorError(
            f"{value!r} is not a colour. Expected a hex string, a colour name, "
            "or a list of RGB(A) components"
        )
    except ColorError as e:
        if field is not None:
            raise ColorError(f"{field}: {e}") from None
        raise


def parse_optional_color(value: Any, field: str | None = None) -> Color | None:
    """Like :func:`parse_color`, but passes ``None`` through untouched, for the
    many parameters whose default is "no colour set"."""
    if value is None:
        return None
    return parse_color(value, field)
