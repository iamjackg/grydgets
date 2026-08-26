"""Widgets must not outlive the tree they were built into.

A theme switch and a SIGUSR1 reload both build a fresh widget tree and drop
the old one. Anything that keeps a dropped widget reachable keeps its whole
subtree -- and the 1080p surfaces those children have cached -- alive with it,
so the process grows every time the theme changes. That is a slow leak on a
Raspberry Pi that switches twice a day and never restarts.

Run with: uv run --with pytest python -m pytest tests/test_widget_teardown.py
"""

import gc
import os
import weakref

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from grydgets.widgets.base import Widget
from grydgets.widgets.widgets import WidgetManager

pygame.init()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No widget built here may reach the network."""

    def refuse(*args, **kwargs):
        raise ConnectionError("tests do not make requests")

    monkeypatch.setattr("grydgets.widgets.containers.requests.request", refuse)
    monkeypatch.setattr("grydgets.rest_fetch.requests.request", refuse)


TREE = {
    "widget": "grid",
    "name": "root",
    "rows": 1,
    "columns": 1,
    "children": [
        {
            "widget": "httpflip",
            "name": "flip",
            "url": "http://localhost/state",
            "mapping": {"on": "lit"},
            "default_widget": "dark",
            "static": True,
            "children": [
                {"widget": "label", "name": "dark", "text": "dark"},
                {"widget": "label", "name": "lit", "text": "lit"},
            ],
        }
    ],
}


def build_tree():
    manager = WidgetManager()
    return manager, manager.create_widget_tree(TREE)


def live_widget_count():
    gc.collect()
    objects = gc.get_objects()
    count = sum(1 for obj in objects if isinstance(obj, Widget))
    del objects
    return count


def test_torn_down_tree_is_collected():
    """Building and stopping a tree repeatedly must not add live widgets.

    Counted against the second cycle rather than the first: the first tree
    warms up module-level state (fonts, loggers) that legitimately stays.
    """
    manager, root = build_tree()
    root.tick()
    baseline = None
    for cycle in range(6):
        new_manager, new_root = build_tree()
        manager.stop_all_widgets(root)
        manager, root = new_manager, new_root
        root.tick()
        if cycle == 1:
            baseline = live_widget_count()
    assert baseline is not None
    assert live_widget_count() == baseline


def test_flip_widget_is_released_after_stop():
    """A stopped httpflip must be collectable, whatever value it last saw.

    Its response-to-child-index lookup is memoised; a cache shared by the
    class would hold on to the instance it was called on.
    """
    dead = []
    for value in ("on", "off", "something-else"):
        manager, root = build_tree()
        flip = root.widget_list[0]
        flip.value = value
        root.tick()
        manager.stop_all_widgets(root)
        dead.append(weakref.ref(flip))
        del manager, root, flip

    gc.collect()
    assert [ref() for ref in dead] == [None, None, None]
