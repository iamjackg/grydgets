"""Tests for grydgets/colors.py, the widget colour parser.

Run with: uv run --with pytest python -m pytest test_colors.py
"""

import pytest

from grydgets.colors import ColorError, parse_color, parse_optional_color


@pytest.mark.parametrize(
    "value,expected",
    [
        # The list form widgets.yaml has always used, with alpha filled in.
        ([255, 136, 0], (255, 136, 0, 255)),
        ([255, 136, 0, 204], (255, 136, 0, 204)),
        ((0, 0, 0), (0, 0, 0, 255)),
        # Hex, long and shorthand, case-insensitive.
        ("#ff8800", (255, 136, 0, 255)),
        ("#FF8800", (255, 136, 0, 255)),
        ("#ff8800cc", (255, 136, 0, 204)),
        ("#f80", (255, 136, 0, 255)),
        ("#f80c", (255, 136, 0, 204)),
        # CSS colour names, courtesy of pygame.Color.
        ("orange", (255, 165, 0, 255)),
        ("red", (255, 0, 0, 255)),
        # Surrounding whitespace is tolerated.
        ("  #ff8800  ", (255, 136, 0, 255)),
    ],
)
def test_accepted_forms(value, expected):
    assert parse_color(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "#ff880",  # 5 digits: not a valid length
        "#gg8800",  # non-hex digits
        "ff8800",  # missing the leading #, ambiguous with a colour name
        "notacolour",
        "",
        [255, 136],  # too few components
        [255, 136, 0, 204, 1],  # too many
        [255, 300, 0],  # out of range
        [255, -1, 0],
        [1, 2, "x"],  # non-integer component
        [1.5, 2, 3],  # floats are not accepted
        42,
        None,
        {"r": 255},
    ],
)
def test_rejected_forms(value):
    with pytest.raises(ColorError):
        parse_color(value)


def test_error_names_the_field():
    with pytest.raises(ColorError) as excinfo:
        parse_color("nope", "bar_color")
    assert "bar_color" in str(excinfo.value)


def test_booleans_are_not_integers():
    # bool is a subclass of int, so this would otherwise sneak through as 1/0.
    with pytest.raises(ColorError):
        parse_color([True, False, True])


def test_parsing_is_stable():
    # A parsed colour fed back in must not change. Widgets compare colours to
    # decide whether to re-render, so drift here means spurious redraws.
    once = parse_color("#ff8800")
    assert parse_color(once) == once


def test_rgb_and_rgba_agree():
    # The same colour written both ways must compare equal after parsing.
    assert parse_color([255, 136, 0]) == parse_color([255, 136, 0, 255])
    assert parse_color("#ff8800") == parse_color([255, 136, 0])


def test_optional_passes_none_through():
    assert parse_optional_color(None) is None
    assert parse_optional_color("#ff8800") == (255, 136, 0, 255)


def test_optional_still_rejects_bad_values():
    with pytest.raises(ColorError):
        parse_optional_color("notacolour")
