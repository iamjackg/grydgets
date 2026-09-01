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

from grydgets import rest_fetch
from grydgets.colors import ColorError
from grydgets.widgets.chart import ProviderBarChartWidget
from grydgets.widgets.containers import GridWidget, PillWidget, ScreenWidget
from grydgets.widgets.image import EmptyWidget
from grydgets.widgets.notifiable import NotifiableTextWidget
from grydgets.widgets.provider_widgets import ProviderTemplateWidget, ProviderWidget
from grydgets.widgets.text import DateClockWidget, LabelWidget, RESTWidget, TextWidget
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
    assert w.grid_widget.widget_background_color == (0, 0, 0, 128)


def test_label_widget_hex():
    w = LabelWidget(text="hi", color="#ff8800")
    assert w.text_widget.color == (255, 136, 0, 255)


def test_screen_widget_hex():
    assert ScreenWidget((10, 10), background_color="#123456").background_color == (
        18,
        52,
        86,
        255,
    )


def test_grid_widget_hex():
    w = GridWidget(
        rows=1,
        columns=1,
        background_color="#ff8800",
        widget_background_color="#00ff0040",
    )
    assert w.background_color == (255, 136, 0, 255)
    assert w.widget_background_color == (0, 255, 0, 64)


def test_grid_widget_colors_stay_none():
    w = GridWidget(rows=1, columns=1)
    assert w.background_color is None
    assert w.widget_background_color is None


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
        "widget_background_color": "#ff8800",
        "children": [{"widget": "label", "text": "hi", "color": "#00ff00"}],
    }
    widget = manager.create_widget_tree(tree)
    assert widget.widget_background_color == (255, 136, 0, 255)
    assert widget.widget_list[0].text_widget.color == (0, 255, 0, 255)


def test_bad_hex_through_widget_manager_raises():
    manager = WidgetManager()
    with pytest.raises(ColorError) as excinfo:
        manager.create_widget_tree(
            {
                "widget": "grid",
                "rows": 1,
                "columns": 1,
                "widget_background_color": "#zzz",
            }
        )
    assert "widget_background_color" in str(excinfo.value)


# The control edits colour as four numeric channels. Indexing a hex string
# yields characters instead, so the filter feeding it must parse first.


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


# These check the rendered pixels rather than the parsed attribute, since a
# background that parses but never reaches the surface would pass either way.


def _pixel(surface, x, y):
    return tuple(surface.get_at((x, y)))


def test_text_background_paints_the_whole_widget():
    w = TextWidget(text="hi", background_color="#ff8800", padding=8)
    surface = w.render((40, 20))
    # Padding insets the text, not the backdrop, so the corner is still filled.
    assert _pixel(surface, 0, 0) == (255, 136, 0, 255)
    assert _pixel(surface, 39, 19) == (255, 136, 0, 255)


def test_text_without_background_stays_transparent():
    w = TextWidget(text="hi")
    surface = w.render((40, 20))
    assert _pixel(surface, 0, 0)[3] == 0


def test_text_corner_radius_clips_the_corner():
    # No text, so every non-transparent pixel is backdrop.
    w = TextWidget(text="", background_color="#ff8800", corner_radius=10)
    surface = w.render((40, 40))
    assert _pixel(surface, 0, 0)[3] == 0
    assert _pixel(surface, 20, 20) == (255, 136, 0, 255)


def test_text_background_alpha_survives():
    w = TextWidget(text="hi", background_color="#00000096")
    surface = w.render((20, 20))
    assert _pixel(surface, 0, 0) == (0, 0, 0, 150)


def test_text_rounded_and_square_backgrounds_agree_on_alpha():
    square = TextWidget(text="hi", background_color="#00000096").render((40, 40))
    rounded = TextWidget(
        text="hi", background_color="#00000096", corner_radius=8
    ).render((40, 40))
    assert _pixel(square, 20, 20) == _pixel(rounded, 20, 20)


def test_set_background_color_marks_dirty():
    w = TextWidget(text="hi")
    w.render((20, 20))
    assert w.is_dirty() is False
    w.set_background_color("#ff8800")
    assert w.is_dirty() is True


def test_set_background_color_to_same_value_stays_clean():
    w = TextWidget(text="hi", background_color="#ff8800")
    w.render((20, 20))
    w.set_background_color([255, 136, 0])
    assert w.is_dirty() is False


def test_provider_forwards_background():
    w = ProviderWidget(
        providers={"p": FakeProvider()},
        background_color="#ff8800",
        corner_radius=12,
    )
    assert w.text_widget.background_color == (255, 136, 0, 255)
    assert w.text_widget.corner_radius == 12


def test_provider_template_forwards_background():
    w = ProviderTemplateWidget(
        providers={"p": FakeProvider()},
        template="{{ 1 }}",
        hass_url="http://localhost",
        hass_token="t",
        background_color="#ff8800",
    )
    assert w.text_widget.background_color == (255, 136, 0, 255)


def test_rest_forwards_background(monkeypatch):
    monkeypatch.setattr(
        rest_fetch, "fetch_text", lambda *a, **kw: rest_fetch.RestTextResult(value="x")
    )
    w = RESTWidget(url="http://example.invalid", background_color="#ff8800", static=True)
    assert w.text_widget.background_color == (255, 136, 0, 255)


def test_provider_accepts_padding_and_align():
    # The wrapper passes padding and align through positionally to TextWidget,
    # so both must stay declared in this widget's own schema.
    w = ProviderWidget(providers={"p": FakeProvider()}, padding=2, align="left")
    assert w.text_widget.padding == 2
    assert w.text_widget.align == "left"


def test_empty_widget_paints_its_colour():
    w = EmptyWidget(color="#ff8800")
    surface = w.render((10, 10))
    assert _pixel(surface, 5, 5) == (255, 136, 0, 255)


def test_empty_widget_without_colour_stays_transparent():
    surface = EmptyWidget().render((10, 10))
    assert _pixel(surface, 5, 5)[3] == 0


def _grid_with_children(**kwargs):
    grid = GridWidget(rows=1, columns=2, **kwargs)
    grid.add_widget(EmptyWidget(name="left"))
    grid.add_widget(EmptyWidget(name="right"))
    return grid


def test_grid_per_cell_colors_by_name():
    grid = _grid_with_children(
        widget_background_colors={"left": "#ff8800", "right": "#0000ff"}
    )
    surface = grid.render((40, 20))
    assert _pixel(surface, 5, 10) == (255, 136, 0, 255)
    assert _pixel(surface, 35, 10) == (0, 0, 255, 255)


def test_grid_per_cell_colors_by_index():
    grid = _grid_with_children(widget_background_colors=["#ff8800", "#0000ff"])
    surface = grid.render((40, 20))
    assert _pixel(surface, 5, 10) == (255, 136, 0, 255)
    assert _pixel(surface, 35, 10) == (0, 0, 255, 255)


def test_grid_per_cell_falls_back_to_the_grid_wide_colour():
    grid = _grid_with_children(
        widget_background_color="#00ff00",
        widget_background_colors=["#ff8800", None],
    )
    surface = grid.render((40, 20))
    assert _pixel(surface, 5, 10) == (255, 136, 0, 255)
    assert _pixel(surface, 35, 10) == (0, 255, 0, 255)


def test_grid_unnamed_child_falls_back():
    grid = GridWidget(
        rows=1, columns=1, widget_background_color="#00ff00",
        widget_background_colors={"nothing-matches-this": "#ff8800"},
    )
    grid.add_widget(EmptyWidget(name="left"))
    surface = grid.render((20, 20))
    assert _pixel(surface, 10, 10) == (0, 255, 0, 255)


def test_grid_per_cell_corner_radii():
    grid = _grid_with_children(
        widget_background_color="#ff8800",
        widget_corner_radii={"left": 9},
    )
    surface = grid.render((40, 40))
    # The left cell is rounded away at its corner, the right one is not.
    assert _pixel(surface, 0, 0)[3] == 0
    assert _pixel(surface, 39, 0) == (255, 136, 0, 255)


def test_grid_per_cell_colors_reject_a_bare_string():
    with pytest.raises(ValueError) as excinfo:
        GridWidget(rows=1, columns=1, widget_background_colors="#ff8800")
    assert "widget_background_colors" in str(excinfo.value)


def test_grid_per_cell_bad_colour_names_the_key():
    with pytest.raises(ColorError) as excinfo:
        GridWidget(rows=1, columns=1, widget_background_colors={"left": "nope"})
    assert "widget_background_colors.left" in str(excinfo.value)


# The old names still load so existing widgets.yaml files keep working.


def test_grid_old_names_still_work():
    old = GridWidget(rows=1, columns=1, color="#ff8800", widget_color="#00ff0040")
    assert old.background_color == (255, 136, 0, 255)
    assert old.widget_background_color == (0, 255, 0, 64)


def test_grid_new_name_wins_when_both_given():
    w = GridWidget(rows=1, columns=1, color="#ff8800", background_color="#0000ff")
    assert w.background_color == (0, 0, 255, 255)


def test_label_old_text_color_still_works():
    assert LabelWidget(text="hi", text_color="#ff8800").text_widget.color == (
        255,
        136,
        0,
        255,
    )


def test_label_defaults_to_white():
    assert LabelWidget(text="hi").text_widget.color == (255, 255, 255, 255)


def test_notification_background_applies():
    w = NotifiableTextWidget(color="#ffffff")
    w.add_widget(TextWidget(text="x"))
    w.notify({"text": "hello", "background_color": "#ff0000"})
    w.tick()
    assert w.text_widget.background_color == (255, 0, 0, 255)


def test_notification_background_resets_between_notifications():
    w = NotifiableTextWidget(color="#ffffff", background_color="#000000")
    w.add_widget(TextWidget(text="x"))

    w.notify({"text": "alert", "background_color": "#ff0000", "duration": 0})
    w.tick()
    assert w.text_widget.background_color == (255, 0, 0, 255)

    # render() is what starts the display timer, so the notification only
    # expires on the tick after a frame has been drawn.
    w.render((10, 10))
    w.tick()
    assert w.showing_text is False

    # Second notification says nothing about colour, so it must not inherit
    # the red backdrop from the first.
    w.notify({"text": "plain"})
    w.tick()
    assert w.text_widget.background_color == (0, 0, 0, 255)


def test_notification_bad_background_is_ignored():
    w = NotifiableTextWidget(color="#ffffff", background_color="#000000")
    w.add_widget(TextWidget(text="x"))
    w.notify({"text": "hello", "background_color": "not-a-colour"})
    w.tick()
    assert w.showing_text is True
    assert w.text_widget.background_color == (0, 0, 0, 255)


# Saving re-applies every field on a node, not just the edited one, so an
# untouched colour must round-trip exactly or it decays into an RGBA list.


def _editor_roundtrip(tmp_path, source, posts):
    from grydgets.editor.app import create_app

    path = tmp_path / "widgets.yaml"
    path.write_text(source)
    app = create_app(str(path))
    client = app.test_client()
    for node_path, data in posts:
        response = client.post(f"/node/{node_path}", data=data)
        assert response.status_code == 200, response.status_code
    client.post("/save")
    return path.read_text()


GRID_SOURCE = """\
background_color: '#101010'
widgets:
  - widget: grid
    rows: 1
    columns: 1
    background_color: '#ff8800'
    widget_background_color: [0, 255, 0]
    corner_radius: 10
    children:
      - widget: text
        text: a
        color: orange
"""

GRID_FORM = {
    "name": "",
    "rows": "1",
    "columns": "1",
    "background_color__0": "255",
    "background_color__1": "136",
    "background_color__2": "0",
    "background_color__3": "255",
    "widget_background_color__0": "0",
    "widget_background_color__1": "255",
    "widget_background_color__2": "0",
    "widget_background_color__3": "255",
    "corner_radius": "20",
}


def test_editor_keeps_hex_when_another_field_changes(tmp_path):
    out = _editor_roundtrip(tmp_path, GRID_SOURCE, [("widgets/0", GRID_FORM)])
    assert "background_color: '#ff8800'" in out
    assert "corner_radius: 20" in out


def test_editor_does_not_append_alpha_to_an_untouched_list(tmp_path):
    out = _editor_roundtrip(tmp_path, GRID_SOURCE, [("widgets/0", GRID_FORM)])
    assert "widget_background_color: [0, 255, 0]" in out


def test_editor_keeps_a_colour_name(tmp_path):
    out = _editor_roundtrip(tmp_path, GRID_SOURCE, [("widgets/0", GRID_FORM)])
    assert "color: orange" in out


def test_editor_writes_a_colour_that_really_changed(tmp_path):
    form = dict(GRID_FORM, background_color__0="0", background_color__1="0")
    out = _editor_roundtrip(tmp_path, GRID_SOURCE, [("widgets/0", form)])
    assert "'#ff8800'" not in out
    # "- 255" is the alpha channel of the block list [0, 0, 0, 255].
    assert "- 255" in out


def test_editor_keeps_the_root_background_hex(tmp_path):
    root_form = {
        "background_image": "",
        "background_color__0": "16",
        "background_color__1": "16",
        "background_color__2": "16",
        "background_color__3": "255",
    }
    out = _editor_roundtrip(tmp_path, GRID_SOURCE, [("root", root_form)])
    assert "background_color: '#101010'" in out


def test_editor_replaces_an_unparseable_colour(tmp_path):
    # Nothing worth preserving about a value that doesn't parse, so the
    # submitted channels win.
    source = GRID_SOURCE.replace("'#ff8800'", "'#zzz'")
    out = _editor_roundtrip(tmp_path, source, [("widgets/0", GRID_FORM)])
    assert "'#zzz'" not in out
