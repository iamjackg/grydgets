"""Tests for graphics.text-scale, which converts the text sizes in
widgets.yaml into the pixels of whichever screen is showing them.

The interesting part is what does *not* scale: a widget with no text_size
fits its text to its own cell, and that cell is already this screen's size.

Run with: uv run --with pytest python -m pytest tests/test_text_scale.py
"""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from grydgets import cli, config, fonts
from grydgets.widgets.text import TextWidget

CONF = """
graphics:
  resolution: [1920, 1080]
  {extra}
logging:
  level: info
server:
  port: 5000
"""


@pytest.fixture(autouse=True)
def reset_scale():
    """Every test gets 1.0, and leaves it that way for the next one."""
    fonts.set_text_scale(1.0)
    yield
    fonts.set_text_scale(1.0)


def load(tmp_path, extra=""):
    path = tmp_path / "conf.yaml"
    path.write_text(CONF.format(extra=extra))
    return config.load_config(str(path))


def apply(tmp_path, extra=""):
    """The scale a conf.yaml ends up with, through the path startup takes."""
    cli.apply_text_scale(load(tmp_path, extra)["graphics"])
    return fonts.get_text_scale()


def test_a_conf_without_the_key_leaves_sizes_alone(tmp_path):
    assert apply(tmp_path) == 1.0


def test_a_configured_scale_is_used(tmp_path):
    assert apply(tmp_path, "text-scale: 1.4") == 1.4


def test_a_whole_number_scale_is_still_a_float(tmp_path):
    assert apply(tmp_path, "text-scale: 2") == 2.0


def test_a_nonsense_scale_is_rejected(tmp_path):
    with pytest.raises(config.ConfigError):
        load(tmp_path, "text-scale: 0")


def test_scaling_rounds_to_a_whole_pixel():
    fonts.set_text_scale(1.4)
    assert fonts.scale_text_size(50) == 70
    assert fonts.scale_text_size(25) == 35
    # 12 * 1.4 is 16.8, and a font size is an integer.
    assert fonts.scale_text_size(12) == 17


def test_scaling_never_reaches_zero():
    fonts.set_text_scale(0.1)
    assert fonts.scale_text_size(1) == 1


def rendered_glyph_height(text_size, scale, cell=(400, 200)):
    """The height of the ink a TextWidget puts on its surface.

    Measured off the pixels rather than by reading back a font size, because
    the size the widget picked is exactly what the test shouldn't have to
    trust.
    """
    pygame.font.init()
    fonts.set_text_scale(scale)
    widget = TextWidget(text="8", text_size=text_size, align="center")
    surface = widget.render(cell)
    box = pygame.mask.from_surface(surface).get_bounding_rects()
    assert box, "nothing was drawn"
    return box[0].height


def test_a_capped_size_grows_with_the_scale():
    plain = rendered_glyph_height(40, 1.0)
    scaled = rendered_glyph_height(40, 2.0)
    # Not exactly double: a glyph is shorter than its font size, and both
    # ends round. Close enough to show the cap was doubled and not ignored.
    assert scaled > plain * 1.8


def test_an_uncapped_size_ignores_the_scale():
    """The cell is this screen's size already, so fitting to it is right."""
    assert rendered_glyph_height(None, 1.0) == rendered_glyph_height(None, 2.0)
