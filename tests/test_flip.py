"""A flip must end its transition on a whole frame of the destination child.

Once a transition finishes, is_dirty() stops reporting the flip as dirty, so
whatever the last render returned stays on screen. On slow hardware, a frame
can start before the transition's end and finish after it.

Run with: uv run --with pytest python -m pytest tests/test_flip.py
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from grydgets.widgets.base import Widget
from grydgets.widgets.containers import FlipWidget, ScheduleFlipWidget

pygame.init()

SIZE = (40, 10)
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now


class SlowSolidWidget(Widget):
    """Fills its area with one colour, and moves the clock on while it draws."""

    def __init__(self, colour, clock, render_seconds, **kwargs):
        super().__init__(**kwargs)
        self.colour = colour
        self.clock = clock
        self.render_seconds = render_seconds

    def is_dirty(self):
        return False

    def render(self, size):
        self.clock.now += self.render_seconds
        surface = pygame.Surface(size, pygame.SRCALPHA, 32)
        surface.fill(self.colour)
        return surface


@pytest.fixture
def clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr("grydgets.widgets.containers.time", clock)
    return clock


def render_until_clean(flip):
    surface = flip.render(SIZE)
    while flip.is_dirty():
        surface = flip.render(SIZE)
    return surface


def only_colour(surface, colour):
    return all(
        tuple(surface.get_at((x, y))) == colour
        for x in range(SIZE[0])
        for y in range(SIZE[1])
    )


def test_flip_settles_on_next_child_after_a_slow_frame(clock):
    flip = FlipWidget(interval=5, transition=1)
    # Each frame takes 1.2s: the first one starts halfway through the
    # transition and ends after it.
    flip.add_widget(SlowSolidWidget(RED, clock, 0.6))
    flip.add_widget(SlowSolidWidget(BLUE, clock, 0.6))

    flip.moving = True
    flip.ticker = clock.now - 0.5

    assert only_colour(render_until_clean(flip), BLUE)
    assert flip.current_widget == 1


def test_scheduleflip_settles_on_destination_after_a_slow_frame(clock):
    flip = ScheduleFlipWidget(schedule={"00:00": "red", "12:00": "blue"}, transition=1)
    flip.add_widget(SlowSolidWidget(RED, clock, 0.6, name="red"))
    flip.add_widget(SlowSolidWidget(BLUE, clock, 0.6, name="blue"))

    flip.current_widget = 0
    flip.destination_widget = 1
    flip.moving = True
    flip.ticker = clock.now - 0.5

    assert only_colour(render_until_clean(flip), BLUE)
    assert flip.current_widget == 1


def test_zero_transition_switches_on_the_first_frame(clock):
    flip = FlipWidget(interval=5, transition=0)
    flip.add_widget(SlowSolidWidget(RED, clock, 0))
    flip.add_widget(SlowSolidWidget(BLUE, clock, 0))

    flip.moving = True
    flip.ticker = clock.now

    assert only_colour(flip.render(SIZE), BLUE)
    assert not flip.is_dirty()
