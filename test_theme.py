"""Tests for grydgets/theme.py, the widgets.yaml theme resolver.

Run with: uv run --with pytest python -m pytest test_theme.py
"""

import pytest
import yaml

from grydgets import config, theme
from grydgets.theme import ThemeError, Token


def load(text):
    """Parse a widgets.yaml body without resolving it, the way the app's
    loader does (config imports register the tag handlers as a side effect)."""
    assert config  # the import is what registers !secret and the token tags
    return yaml.load(text, Loader=yaml.FullLoader)


def resolve(text):
    return theme.apply_theme(load(text))


THEME = """
theme:
  colors:
    panel: '#3b4252'
    text: '#eceff4'
  fonts:
    regular: fonts/Inter-400.ttf
  sizes:
    radius: 25
"""


# --- parsing -------------------------------------------------------------


def test_tag_parses_to_a_token():
    doc = load("widgets: [{widget: text, color: !color panel}]")
    assert doc["widgets"][0]["color"] == Token("color", "panel")


def test_secret_still_has_its_own_constructor(tmp_path, monkeypatch):
    """The token tags are registered as a prefix handler, so this checks
    !secret's exact-tag constructor still wins over it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secrets.yaml").write_text("hass_token: shhh\n")
    # Clear the module's memoised secrets so the tmp file is the one read.
    monkeypatch.setitem(getattr(config, "__SECRETS"), "main_secrets", {})
    doc = load("widgets: [{widget: rest, auth: {bearer: !secret hass_token}}]")
    value = doc["widgets"][0]["auth"]["bearer"]
    assert not isinstance(value, Token)
    assert value == "shhh"


def test_a_dollar_in_a_string_is_left_alone():
    """The reason for tags over a $name sentinel: these are real values."""
    doc = resolve(
        THEME
        + """
widgets:
  - widget: provider
    jq_expression: '$__loc__ | .value'
    format_string: '${:.2f}'
    text: 'costs $5'
"""
    )
    node = doc["widgets"][0]
    assert node["jq_expression"] == "$__loc__ | .value"
    assert node["format_string"] == "${:.2f}"
    assert node["text"] == "costs $5"


# --- token resolution ----------------------------------------------------


def test_tokens_resolve_from_their_section():
    doc = resolve(
        THEME
        + """
widgets:
  - widget: text
    color: !color panel
    font_path: !font regular
    corner_radius: !size radius
"""
    )
    node = doc["widgets"][0]
    assert node["color"] == "#3b4252"
    assert node["font_path"] == "fonts/Inter-400.ttf"
    assert node["corner_radius"] == 25


def test_a_singular_section_name_also_works():
    doc = resolve(
        """
theme:
  color:
    panel: '#3b4252'
widgets: [{widget: text, color: !color panel}]
"""
    )
    assert doc["widgets"][0]["color"] == "#3b4252"


def test_tokens_resolve_below_the_widget_tree():
    """Colours nested inside a mapping or list parameter, e.g. a grid's
    per-cell overrides, which the resolver never has to know the shape of."""
    doc = resolve(
        THEME
        + """
widgets:
  - widget: grid
    widget_background_colors:
      left: !color panel
    bar_colors: [!color text, null, !color panel]
"""
    )
    node = doc["widgets"][0]
    assert node["widget_background_colors"] == {"left": "#3b4252"}
    assert node["bar_colors"] == ["#eceff4", None, "#3b4252"]


def test_top_level_keys_are_resolved_too():
    """cli.py reads background_color straight off the document, not through
    the widget tree builder."""
    doc = resolve(THEME + "background_color: !color panel\nwidgets: []\n")
    assert doc["background_color"] == "#3b4252"


def test_a_theme_entry_may_reference_another():
    doc = resolve(
        """
theme:
  colors:
    base: '#3b4252'
    panel: !color base
widgets: [{widget: text, color: !color panel}]
"""
    )
    assert doc["widgets"][0]["color"] == "#3b4252"


def test_the_theme_block_survives_resolved():
    doc = resolve(THEME + "widgets: []\n")
    assert doc["theme"]["colors"]["panel"] == "#3b4252"


# --- token errors --------------------------------------------------------


def test_unknown_entry_names_the_section_and_its_contents():
    with pytest.raises(ThemeError) as excinfo:
        resolve(THEME + "widgets: [{widget: text, color: !color pnael}]")
    message = str(excinfo.value)
    assert "!color pnael" in message
    assert "panel" in message
    assert "widgets[0].color" in message


def test_unknown_section_lists_the_ones_that_exist():
    with pytest.raises(ThemeError) as excinfo:
        resolve(THEME + "widgets: [{widget: text, color: !colour panel}]")
    assert "!colour" in str(excinfo.value)
    assert "colors" in str(excinfo.value)


def test_a_token_with_no_theme_block_at_all_errors():
    with pytest.raises(ThemeError):
        resolve("widgets: [{widget: text, color: !color panel}]")


def test_a_cycle_is_reported_rather_than_recursing_forever():
    with pytest.raises(ThemeError) as excinfo:
        resolve(
            """
theme:
  colors:
    a: !color b
    b: !color a
widgets: [{widget: text, color: !color a}]
"""
        )
    assert "loop" in str(excinfo.value)


def test_tokens_are_rejected_in_conf_yaml(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("graphics:\n  resolution: !size screen\n")
    with pytest.raises(ThemeError) as excinfo:
        config.load_config(str(path))
    assert "widgets file" in str(excinfo.value)


# --- defaults ------------------------------------------------------------


DEFAULTS = """
theme:
  colors:
    text: '#eceff4'
  fonts:
    regular: fonts/Inter-400.ttf
  groups:
    text-like: [text, rest, provider]
  defaults:
    text-like:
      font_path: !font regular
      color: !color text
    grid:
      widget_corner_radius: 25
"""


def test_group_defaults_reach_every_member_type():
    doc = resolve(
        DEFAULTS
        + """
widgets:
  - widget: grid
    children:
      - widget: text
      - widget: rest
        url: http://example.invalid
      - widget: provider
"""
    )
    grid = doc["widgets"][0]
    assert grid["widget_corner_radius"] == 25
    for child in grid["children"]:
        assert child["font_path"] == "fonts/Inter-400.ttf"
        assert child["color"] == "#eceff4"


def test_a_widget_that_sets_the_parameter_keeps_its_own_value():
    doc = resolve(DEFAULTS + "widgets: [{widget: text, color: '#bf616a'}]")
    node = doc["widgets"][0]
    assert node["color"] == "#bf616a"
    assert node["font_path"] == "fonts/Inter-400.ttf"


def test_defaults_do_not_reach_types_outside_the_group():
    doc = resolve(DEFAULTS + "widgets: [{widget: image}]")
    assert "font_path" not in doc["widgets"][0]


def test_naming_a_type_outright_beats_the_group_it_belongs_to():
    doc = resolve(
        """
theme:
  fonts:
    regular: regular.ttf
    bold: bold.ttf
  groups:
    text-like: [text, rest]
  defaults:
    text-like:
      font_path: !font regular
    text:
      font_path: !font bold
widgets: [{widget: text}, {widget: rest, url: http://example.invalid}]
"""
    )
    assert doc["widgets"][0]["font_path"] == "bold.ttf"
    assert doc["widgets"][1]["font_path"] == "regular.ttf"


def test_a_defaulted_list_is_not_shared_between_nodes():
    doc = resolve(
        """
theme:
  defaults:
    text:
      color: [59, 66, 82]
widgets: [{widget: text}, {widget: text}]
"""
    )
    first, second = doc["widgets"]
    assert first["color"] == second["color"]
    assert first["color"] is not second["color"]


def test_defaults_apply_at_every_depth():
    doc = resolve(
        DEFAULTS
        + """
widgets:
  - widget: grid
    children:
      - widget: flip
        children:
          - widget: text
"""
    )
    deep = doc["widgets"][0]["children"][0]["children"][0]
    assert deep["color"] == "#eceff4"


def test_theme_entries_are_not_treated_as_widget_nodes():
    """A theme value that happens to be a mapping with a `widget` key is data,
    not part of the tree."""
    doc = resolve(
        """
theme:
  blobs:
    thing: {widget: text}
  defaults:
    text:
      color: '#eceff4'
widgets: []
"""
    )
    assert "color" not in doc["theme"]["blobs"]["thing"]


# --- malformed theme blocks ----------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "theme: [1, 2]\nwidgets: []\n",
        "theme:\n  groups: [text]\n  defaults: {}\nwidgets: []\n",
        "theme:\n  defaults:\n    text: notamapping\nwidgets: []\n",
        "theme:\n  groups:\n    g: notalist\n  defaults:\n    g: {}\nwidgets: []\n",
        "theme:\n  colors: notamapping\nwidgets: [{widget: text, color: !color x}]\n",
    ],
)
def test_malformed_theme_blocks_raise(body):
    with pytest.raises(ThemeError):
        resolve(body)


def test_a_document_with_no_theme_is_unchanged():
    text = "widgets: [{widget: text, color: '#bf616a'}]\n"
    assert resolve(text) == load(text)
