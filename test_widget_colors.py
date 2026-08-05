"""Colour parsing as it reaches widgets through the normal config path.

test_colors.py covers the parser itself; this covers the wiring -- that every
widget parameter documented as a colour actually goes through the parser, and
that a hex string and the equivalent list produce identical widgets.

Run with: uv run --with pytest python -m pytest test_widget_colors.py
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from grydgets.colors import ColorError
from grydgets.widgets.chart import ProviderBarChartWidget
from grydgets.widgets.containers import GridWidget, PillWidget, ScreenWidget
from grydgets.widgets.notifiable import NotifiableTextWidget
from grydgets.widgets.text import DateClockWidget, LabelWidget, TextWidget
from grydgets.widgets.widgets import WidgetManager

pygame.init()


class FakeProvider:
    """Minimal stand-in for a DataProvider; the chart only needs these."""

    def get_timestamp(self):
        return 0

    def get_data(self):
        return None

    def get_error(self):
        return None


def test_text_widget_hex():
    assert TextWidget(color="#ff8800").color == (255, 136, 0, 255)


def test_text_widget_hex_matches_list():
    assert TextWidget(color="#ff8800").color == TextWidget(color=[255, 136, 0]).color


def test_dateclock_per_line_colors():
    w = DateClockWidget(color="#111111", time_color="#ff8800", date_color="teal")
    assert w.hour_widget.color == (255, 136, 0, 255)
    assert w.date_widget.color == (0, 128, 128, 255)


def test_dateclock_falls_back_to_color():
    w = DateClockWidget(color="#ff8800")
    assert w.hour_widget.color == (255, 136, 0, 255)
    assert w.date_widget.color == (255, 136, 0, 255)


def test_dateclock_background_hex():
    w = DateClockWidget(background_color="#00000080")
    assert w.grid_widget.widget_color == (0, 0, 0, 128)


def test_label_widget_hex():
    w = LabelWidget(text="hi", text_color="#ff8800")
    assert w.text_widget.color == (255, 136, 0, 255)


def test_screen_widget_hex():
    assert ScreenWidget((10, 10), color="#123456").color == (18, 52, 86, 255)


def test_grid_widget_hex():
    w = GridWidget(rows=1, columns=1, color="#ff8800", widget_color="#00ff0040")
    assert w.color == (255, 136, 0, 255)
    assert w.widget_color == (0, 255, 0, 64)


def test_grid_widget_colors_stay_none():
    w = GridWidget(rows=1, columns=1)
    assert w.color is None
    assert w.widget_color is None


def test_pill_widget_hex():
    w = PillWidget(widget_background_color="#ff8800", pill_background_color="#0f0")
    assert w.widget_background_color == (255, 136, 0, 255)
    assert w.pill_background_color == (0, 255, 0, 255)


def test_notifiable_text_hex():
    w = NotifiableTextWidget(color="#ff8800")
    assert w.text_widget.color == (255, 136, 0, 255)


def test_chart_flat_and_nested_colors():
    w = ProviderBarChartWidget(
        providers={"p": FakeProvider()},
        bar_color="#ff8800",
        bar_colors={"mon": "#ff0000", "tue": [0, 255, 0]},
        bar_background_colors={"mon": "#0000ff80"},
        bar_color_thresholds=[
            {"above": 10, "color": "#ff0000"},
            {"above": 5, "color": "orange"},
        ],
        midline_color="#111",
        quartline_color="#222",
        label_color="#333",
    )
    assert w.bar_color == (255, 136, 0, 255)
    assert w.bar_colors == {"mon": (255, 0, 0, 255), "tue": (0, 255, 0, 255)}
    assert w.bar_background_colors == {"mon": (0, 0, 255, 128)}
    # Thresholds are sorted descending by "above".
    assert [t["above"] for t in w.bar_color_thresholds] == [10.0, 5.0]
    assert w.bar_color_thresholds[0]["color"] == (255, 0, 0, 255)
    assert w.bar_color_thresholds[1]["color"] == (255, 165, 0, 255)
    assert w.midline_color == (17, 17, 17, 255)
    assert w.label_color == (51, 51, 51, 255)


def test_chart_bad_nested_color_names_the_key():
    with pytest.raises(ColorError) as excinfo:
        ProviderBarChartWidget(
            providers={"p": FakeProvider()},
            bar_colors={"mon": "nope"},
        )
    assert "bar_colors.mon" in str(excinfo.value)


def test_notification_color_does_not_crash_the_widget():
    # A bad colour arrives over HTTP, not from config, so it must be ignored
    # rather than taking down the render loop.
    w = NotifiableTextWidget(color="#ffffff")
    w.add_widget(TextWidget(text="x"))
    w.notify({"text": "hello", "color": "not-a-colour"})
    w.tick()
    assert w.showing_text is True
    assert w.text_widget.color == (255, 255, 255, 255)


def test_notification_color_applies_when_valid():
    w = NotifiableTextWidget(color="#ffffff")
    w.add_widget(TextWidget(text="x"))
    w.notify({"text": "hello", "color": "#ff8800"})
    w.tick()
    assert w.text_widget.color == (255, 136, 0, 255)


def test_set_color_does_not_dirty_on_equivalent_value():
    # (255,136,0) and (255,136,0,255) are the same colour; re-setting one as
    # the other must not mark the widget dirty and force a redraw.
    w = TextWidget(color=[255, 136, 0])
    w.render((50, 20))
    assert w.is_dirty() is False
    w.set_color("#ff8800")
    assert w.is_dirty() is False
    w.set_color("#00ff00")
    assert w.is_dirty() is True


def test_hex_through_widget_manager():
    # The real path: a widgets.yaml fragment built by WidgetManager.
    manager = WidgetManager()
    tree = {
        "widget": "grid",
        "rows": 1,
        "columns": 1,
        "widget_color": "#ff8800",
        "children": [{"widget": "label", "text": "hi", "text_color": "#00ff00"}],
    }
    widget = manager.create_widget_tree(tree)
    assert widget.widget_color == (255, 136, 0, 255)
    assert widget.widget_list[0].text_widget.color == (0, 255, 0, 255)


def test_bad_hex_through_widget_manager_raises():
    manager = WidgetManager()
    with pytest.raises(ColorError) as excinfo:
        manager.create_widget_tree(
            {"widget": "grid", "rows": 1, "columns": 1, "widget_color": "#zzz"}
        )
    assert "widget_color" in str(excinfo.value)


# --- editor colour control -------------------------------------------------
# The control edits colours as four numeric channels. Indexing a hex *string*
# yields its characters, which the control would then write back on Apply, so
# the filter that feeds it has to parse first.


def test_editor_color_channels_from_hex():
    from grydgets.editor.app import _color_channels_filter

    assert _color_channels_filter("#00000096") == [0, 0, 0, 150]


def test_editor_color_channels_match_between_forms():
    from grydgets.editor.app import _color_channels_filter

    assert _color_channels_filter("#ff8800") == _color_channels_filter([255, 136, 0])


def test_editor_color_channels_tolerate_junk():
    from grydgets.editor.app import _color_channels_filter

    # An unparseable value leaves the boxes empty rather than being guessed at.
    assert _color_channels_filter("not-a-colour") == []
    assert _color_channels_filter(None) == []
