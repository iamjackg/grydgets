"""Tests for where TextWidget puts its text.

Run with: uv run --with pytest python -m pytest tests/test_text_layout.py
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from grydgets import fonts
from grydgets.widgets.text import TextWidget

DEFAULT_FONT_FILE = os.path.join(os.path.dirname(pygame.__file__), "freesansbold.ttf")


@pytest.fixture(autouse=True)
def pygame_running():
    # Other test modules shut pygame down when they finish.
    pygame.init()


def ink(widget, size):
    """The bounding box of everything the widget drew."""
    return widget.render(size).get_bounding_rect()


@pytest.mark.parametrize("size", [12, 100, 228])
def test_default_font_is_the_size_asked_for(size):
    built_in = fonts.FontCache().get_font(None, size)
    from_file = pygame.font.Font(DEFAULT_FONT_FILE, size)
    assert built_in.get_height() == from_file.get_height()


def test_centred_default_font_text_is_centred():
    rect = ink(TextWidget(text="Hello", align="center", vertical_align="center"), (400, 480))
    assert abs(rect.centerx - 200) <= 5
    assert abs(rect.centery - 240) <= 15


def test_right_aligned_text_ends_at_the_right_edge():
    rect = ink(TextWidget(text="Hi", text_size=40, align="right"), (400, 100))
    assert rect.right >= 395


def test_left_aligned_text_starts_at_the_left_edge():
    rect = ink(TextWidget(text="Hi", text_size=40), (400, 100))
    assert rect.left <= 5
