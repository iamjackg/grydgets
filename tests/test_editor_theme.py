"""Tests for the widgets.yaml editor's handling of theme tokens.

The editor edits a ruamel round-trip document, so a token is a TaggedScalar
that every plain form control would flatten into a literal on the way back.
These tests drive the real Flask routes and assert on the document the editor
would save.

Run with: uv run --with pytest python -m pytest test_editor_theme.py
"""

import pytest
from werkzeug.datastructures import MultiDict

from grydgets import theme
from grydgets.editor import theme_ui, yamlio
from grydgets.editor.app import create_app
from grydgets.editor.schema import FieldSpec

SAMPLE = """\
theme:
  colors:
    panel: [0, 0, 0, 150]
    text: '#eceff4'
  fonts:
    regular: OpenSans-Regular.ttf
    bold: OpenSans-ExtraBold.ttf
  images:
    screen: bgcolorlight.jpg
  sizes:
    radius: 25

  groups:
    text-like: [text, rest, notifiabletext, provider]
  defaults:
    text-like:
      font_path: !font regular
      color: !color text
    provider:
      providers: [shared]
      color: [9, 9, 9]
    grid:
      padding: !size radius

widgets:
  - widget: grid
    name: root
    rows: 6
    columns: 1
    row_ratios: [4, 1]
    widget_corner_radius: !size radius
    widget_background_colors:
      '0,0': !color panel
    children:
      - widget: text
        name: titled
        text: hello
        font_path: !font bold
        color: !color text
        corner_radius: !size radius
        text_size: 40
      - widget: text
        name: plain
        text: !color panel
        font_path: fonts/Other.ttf
        color: [1, 2, 3]
      - widget: provider
        name: fetch
        providers: [work_calendar]
        auth:
          bearer: !secret hass_token

        text_size: 20  # how big the value renders
      - widget: notifiabletext
        name: needs-font
        text_size: 30
      - widget: provider
        name: inherit-a
      - widget: provider
        name: inherit-b
"""


@pytest.fixture
def editor(tmp_path):
    path = tmp_path / "widgets.yaml"
    path.write_text(SAMPLE)
    app = create_app(str(path))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(editor):
    return editor.test_client()


def doc_of(editor):
    return editor.config["STATE"].doc


def node_named(editor, name):
    for widget in doc_of(editor)["widgets"]:
        for candidate in [widget] + list(widget.get("children") or []):
            if candidate.get("name") == name:
                return candidate
    raise AssertionError(f"no node named {name}")


def apply_to(client, path, **fields):
    return client.post(f"/node/{path}", data=MultiDict(list(fields.items())))


TITLED = "widgets/0/children/0"
PLAIN = "widgets/0/children/1"
FETCH = "widgets/0/children/2"
NEEDS_FONT = "widgets/0/children/3"
INHERIT_A = "widgets/0/children/4"
INHERIT_B = "widgets/0/children/5"
ROOT_GRID = "widgets/0"


def is_token(value, section, name):
    return yamlio.is_theme_token(value) and yamlio.token_parts(value) == (section, name)


# --------------------------------------------------------------------------
# theme.section_for_tag / theme_ui field mapping
# --------------------------------------------------------------------------


def test_section_for_tag_accepts_both_spellings():
    assert theme.section_for_tag({"colors": {"a": 1}}, "color") == {"a": 1}
    assert theme.section_for_tag({"color": {"a": 1}}, "color") == {"a": 1}
    assert theme.section_for_tag({"fonts": {}}, "size") is None


@pytest.mark.parametrize(
    "name, control, expected",
    [
        ("color", "color", "color"),
        ("widget_background_color", "color", "color"),
        ("font_path", "text", "font"),
        ("label_font_path", "text", "font"),
        ("image_path", "text", "image"),
        ("background_image", "text", "image"),
        ("corner_radius", "number", "size"),
        ("text", "text", None),
        ("align", "select", None),
        ("drop_shadow", "checkbox", None),
    ],
)
def test_tag_for_field(name, control, expected):
    assert theme_ui.tag_for_field(FieldSpec(name, control=control)) == expected


def test_token_options_read_the_document_not_a_fixed_list(editor):
    doc = doc_of(editor)
    options = theme_ui.token_options(doc, FieldSpec("corner_radius", control="number"))
    assert [o.form_value for o in options] == ["size radius"]

    # A theme with no sizes section offers nothing on a numeric field, rather
    # than an empty picker.
    del doc["theme"]["sizes"]
    assert theme_ui.token_options(doc, FieldSpec("corner_radius", control="number")) == []


# --------------------------------------------------------------------------
# A no-op Apply must not touch anything
# --------------------------------------------------------------------------


def test_reapplying_a_node_unchanged_keeps_every_token(client, editor):
    before = yamlio.dump_doc_to_string(doc_of(editor))
    for path in (ROOT_GRID, TITLED, PLAIN):
        html = client.get(f"/node/{path}/inspect").get_data(as_text=True)
        assert "TaggedScalar" not in html  # never leak the repr into a form
    apply_to(
        client,
        TITLED,
        name="titled",
        text="hello",
        font_path_kind="theme",
        font_path_token="font bold",
        color_kind="theme",
        color_token="color text",
        corner_radius_kind="theme",
        corner_radius_token="size radius",
        text_size="40",
    )
    assert yamlio.dump_doc_to_string(doc_of(editor)) == before


def test_number_control_cannot_delete_a_token(client, editor):
    """A browser can't show `radius` in <input type=number>, so it posts an
    empty string -- which used to pop the key."""
    apply_to(
        client,
        TITLED,
        name="titled",
        text="hello",
        font_path_kind="theme",
        font_path_token="font bold",
        color_kind="theme",
        color_token="color text",
        corner_radius_kind="theme",
        corner_radius_token="size radius",
        corner_radius="",
        text_size="40",
    )
    assert is_token(node_named(editor, "titled")["corner_radius"], "size", "radius")


# --------------------------------------------------------------------------
# Switching a field between a plain value and a token
# --------------------------------------------------------------------------


def test_plain_value_can_be_switched_to_a_token(client, editor):
    apply_to(
        client,
        PLAIN,
        name="plain",
        text="",
        font_path_kind="theme",
        font_path_token="font regular",
        color_kind="plain",
        color__0="1", color__1="2", color__2="3",
    )
    node = node_named(editor, "plain")
    assert is_token(node["font_path"], "font", "regular")
    assert "!font regular" in yamlio.dump_doc_to_string(doc_of(editor))


def test_token_can_be_switched_back_to_a_plain_value(client, editor):
    apply_to(
        client,
        TITLED,
        name="titled",
        text="hello",
        font_path_kind="plain",
        font_path="fonts/Replacement.ttf",
        color_kind="theme",
        color_token="color text",
        corner_radius_kind="theme",
        corner_radius_token="size radius",
        text_size="40",
    )
    assert node_named(editor, "titled")["font_path"] == "fonts/Replacement.ttf"


def test_switching_off_theme_without_a_replacement_keeps_the_token(client, editor):
    response = apply_to(
        client,
        TITLED,
        name="titled",
        text="hello",
        font_path_kind="plain",
        font_path="",
        color_kind="theme",
        color_token="color text",
        corner_radius_kind="theme",
        corner_radius_token="size radius",
        text_size="40",
    )
    assert is_token(node_named(editor, "titled")["font_path"], "font", "bold")
    assert "enter a value to replace the theme token" in response.get_data(as_text=True)


def test_choosing_theme_without_picking_an_entry_is_an_error(client, editor):
    response = apply_to(
        client,
        TITLED,
        name="titled",
        text="hello",
        font_path_kind="theme",
        font_path_token="",
        color_kind="theme",
        color_token="color text",
        corner_radius_kind="theme",
        corner_radius_token="size radius",
        text_size="40",
    )
    assert is_token(node_named(editor, "titled")["font_path"], "font", "bold")
    assert "pick a theme value" in response.get_data(as_text=True)


def test_colour_token_survives_the_channel_boxes_being_blank(client, editor):
    """The colour control renders empty for a token; that is not an edit."""
    apply_to(
        client,
        TITLED,
        name="titled",
        text="hello",
        font_path_kind="theme",
        font_path_token="font bold",
        color_kind="theme",
        color_token="color text",
        color__0="", color__1="", color__2="", color__3="",
        corner_radius_kind="theme",
        corner_radius_token="size radius",
        text_size="40",
    )
    assert is_token(node_named(editor, "titled")["color"], "color", "text")


# --------------------------------------------------------------------------
# Tokens no control can carry are read-only
# --------------------------------------------------------------------------


def test_token_on_a_field_with_no_picker_is_left_alone(client, editor):
    """`text:` is a string with no theme section behind it, so the inspector
    shows the token as written and Apply must not flatten it."""
    html = client.get(f"/node/{PLAIN}/inspect").get_data(as_text=True)
    assert "!color panel" in html

    apply_to(
        client,
        PLAIN,
        name="plain",
        text="panel",  # what the text input would have posted back
        font_path_kind="plain",
        font_path="fonts/Other.ttf",
        color_kind="plain",
        color__0="1", color__1="2", color__2="3",
    )
    assert is_token(node_named(editor, "plain")["text"], "color", "panel")


def test_nested_token_in_a_raw_field_round_trips(client, editor):
    """A raw YAML box is parsed back with ruamel, so a tag inside it lives."""
    apply_to(
        client,
        ROOT_GRID,
        name="root",
        rows="2",
        columns="1",
        row_ratios="4\n1",
        widget_corner_radius_kind="theme",
        widget_corner_radius_token="size radius",
        widget_background_colors="'0,0': !color panel\n",
    )
    node = node_named(editor, "root")
    assert is_token(node["widget_background_colors"]["0,0"], "color", "panel")
    assert "!color panel" in yamlio.dump_doc_to_string(doc_of(editor))


# --------------------------------------------------------------------------
# Numbers keep the form they were written in
# --------------------------------------------------------------------------


def test_whole_numbers_stay_integers(client, editor):
    apply_to(
        client,
        ROOT_GRID,
        name="root",
        rows="2",
        columns="1",
        row_ratios="4\n1",
        widget_corner_radius_kind="theme",
        widget_corner_radius_token="size radius",
        widget_background_colors="'0,0': !color panel\n",
    )
    node = node_named(editor, "root")
    assert node["row_ratios"] == [4, 1]
    assert all(isinstance(v, int) for v in node["row_ratios"])
    assert "row_ratios: [4, 1]" in yamlio.dump_doc_to_string(doc_of(editor))


def test_list_keeps_the_style_it_was_written_in(client, editor):
    apply_to(
        client,
        FETCH,
        name="fetch",
        providers="work_calendar",
        text_size="20",
    )
    dumped = yamlio.dump_doc_to_string(doc_of(editor))
    assert "providers: [work_calendar]" in dumped


def test_editing_a_node_keeps_its_comments_and_spacing(client, editor):
    """auth used to be replaced with a fresh mapping, which threw away the
    blank line and comment ruamel had attached around it."""
    before = yamlio.dump_doc_to_string(doc_of(editor))
    apply_to(
        client,
        FETCH,
        name="fetch",
        providers="work_calendar",
        text_size="20",
        auth_type="bearer",
        auth_bearer_kind="secret",
        auth_bearer_secret_key="hass_token",
    )
    assert yamlio.dump_doc_to_string(doc_of(editor)) == before
    assert "# how big the value renders" in before


@pytest.mark.parametrize(
    "raw, json_type, expected",
    [
        ("4", "number", 4),
        ("4", "integer", 4),
        ("4.5", "number", 4.5),
        ("4.0", "number", 4.0),
        ("1e3", "number", 1000.0),
        (" 7 ", "number", 7),
    ],
)
def test_parse_number(raw, json_type, expected):
    from grydgets.editor.app import _parse_number

    result = _parse_number(raw, json_type)
    assert result == expected
    assert isinstance(result, type(expected))


# --------------------------------------------------------------------------
# Fields the theme supplies
# --------------------------------------------------------------------------


def test_defaults_carry_the_entry_they_came_from():
    parsed = yamlio.parse_value(SAMPLE)
    by_type = theme.defaults_with_source(parsed["theme"])
    assert by_type["text"]["font_path"][1] == "text-like"
    # A widget type named outright beats the group it is also a member of,
    # and says so.
    assert by_type["provider"]["color"] == ([9, 9, 9], "provider")
    assert by_type["text"]["color"][1] == "text-like"
    # ...and the plain view still agrees with it.
    plain = theme.defaults_by_widget_type(parsed["theme"])
    assert plain["provider"]["color"] == [9, 9, 9]


def test_inherited_field_is_shown_with_its_source_and_value(client):
    html = client.get(f"/node/{INHERIT_A}/inspect").get_data(as_text=True)
    assert "from theme: text-like" in html
    assert "!font regular" in html                      # what the theme says
    assert 'value="OpenSans-Regular.ttf" disabled' in html  # what it resolves to
    assert "override-field" in html


def test_inherited_fields_are_not_written_by_an_apply(client, editor):
    """Even when the form posts them -- the disabled controls are the display
    half of the rule, update_node is the half that counts."""
    apply_to(
        client,
        INHERIT_A,
        name="inherit-a",
        font_path="OpenSans-Regular.ttf",
        providers="shared",
        color__0="9", color__1="9", color__2="9",
    )
    node = node_named(editor, "inherit-a")
    assert "font_path" not in node
    assert "color" not in node
    assert "providers" not in node


def test_required_field_supplied_by_the_theme_is_not_blanked(client, editor):
    """font_path is required for notifiabletext. Rendered as an empty input
    it came back as "" and shadowed the theme."""
    html = client.get(f"/node/{NEEDS_FONT}/inspect").get_data(as_text=True)
    assert "from theme: text-like" in html

    apply_to(client, NEEDS_FONT, name="needs-font", font_path="", text_size="30")
    assert "font_path" not in node_named(editor, "needs-font")


def test_override_copies_the_value_onto_the_node(client, editor):
    client.post(
        f"/node/{INHERIT_A}/override-field", data={"field_name": "font_path"}
    )
    # The default is written as a token, so the node gets the token -- from
    # there the picker from item 2 takes over.
    assert is_token(node_named(editor, "inherit-a")["font_path"], "font", "regular")

    client.post(f"/node/{INHERIT_A}/override-field", data={"field_name": "color"})
    assert node_named(editor, "inherit-a")["color"] == [9, 9, 9]


def test_two_nodes_overriding_one_default_do_not_share_it(client, editor):
    for path in (INHERIT_A, INHERIT_B):
        client.post(f"/node/{path}/override-field", data={"field_name": "providers"})

    node_named(editor, "inherit-a")["providers"].append("extra")
    assert node_named(editor, "inherit-b")["providers"] == ["shared"]


def test_override_then_remove_falls_back_to_the_theme(client, editor):
    client.post(
        f"/node/{INHERIT_A}/override-field", data={"field_name": "font_path"}
    )
    assert "font_path" in node_named(editor, "inherit-a")

    response = client.delete(f"/node/{INHERIT_A}/field/font_path")
    assert "font_path" not in node_named(editor, "inherit-a")
    # ...and it is back to being shown as inherited.
    assert "from theme: text-like" in response.get_data(as_text=True)


def test_overridden_field_says_what_it_overrides(client):
    """`titled` sets font_path itself, and the theme would otherwise give it
    one, so removing it has a destination worth naming."""
    html = client.get(f"/node/{TITLED}/inspect").get_data(as_text=True)
    assert "overrides theme: text-like" in html
    assert "fall back to the theme default from 'text-like'" in html


def test_add_property_menu_skips_what_the_theme_supplies(client):
    html = client.get(f"/node/{INHERIT_A}/inspect").get_data(as_text=True)
    menu = html[html.find("add property"):]
    assert '<option value="font_path">' not in menu
    assert '<option value="color">' not in menu
    assert '<option value="text_size">' in menu  # nothing supplies this one


def test_test_panel_sees_defaults_and_resolved_tokens(editor, tmp_path):
    """A node whose parameters come from the theme has to be tested with
    them, not as an empty request."""
    from grydgets.editor import rest_test

    doc = doc_of(editor)
    doc["theme"]["urls"] = {"hass": "http://hass.invalid/api/x"}
    doc["theme"]["defaults"]["provider"]["data_path"] = "state"

    node = node_named(editor, "inherit-a")
    node["url"] = yamlio.make_token("url", "hass")

    params = rest_test.resolve_node(
        node,
        str(tmp_path / "secrets.yaml"),
        theme.theme_sections(doc),
        theme.defaults_with_source(doc["theme"])["provider"],
    )
    assert params["url"] == "http://hass.invalid/api/x"   # token resolved
    assert params["data_path"] == "state"                 # default filled in
    assert params["font_path"] == "OpenSans-Regular.ttf"  # default, then token
    assert "url" in node                                  # node itself untouched
    assert yamlio.is_theme_token(node["url"])


# --------------------------------------------------------------------------
# The document's own background_color
# --------------------------------------------------------------------------


def test_root_background_colour_token_is_not_dropped(client, editor):
    doc = doc_of(editor)
    doc["background_color"] = yamlio.make_token("color", "panel")

    client.post(
        "/node/root",
        data=MultiDict([
            ("background_image", ""),
            ("background_color_kind", "theme"),
            ("background_color_token", "color panel"),
            ("background_color__0", ""),
            ("background_color__1", ""),
            ("background_color__2", ""),
            ("background_color__3", ""),
        ]),
    )
    assert is_token(doc["background_color"], "color", "panel")


# --------------------------------------------------------------------------
# The document's own background_image
# --------------------------------------------------------------------------


def root_form(**overrides):
    """What the root inspector's form posts, with the fields a browser always
    sends filled in blank so a test only has to name what it's exercising."""
    fields = {
        "background_image": "",
        "background_image_kind": "plain",
        "background_image_token": "",
        "background_color_kind": "plain",
        "background_color_token": "",
        "background_color__0": "",
        "background_color__1": "",
        "background_color__2": "",
        "background_color__3": "",
    }
    fields.update(overrides)
    return MultiDict(list(fields.items()))


def test_root_background_image_offers_the_theme_images(client, editor):
    options = theme_ui.token_options(doc_of(editor), FieldSpec("background_image"))
    assert [(o.tag, o.name) for o in options] == [("image", "screen")]


def test_root_background_image_token_is_applied(client, editor):
    doc = doc_of(editor)
    client.post(
        "/node/root",
        data=root_form(
            background_image_kind="theme", background_image_token="image screen"
        ),
    )
    assert is_token(doc["background_image"], "image", "screen")


def test_root_background_image_token_renders_as_an_empty_box(client, editor):
    """The text control has no way to show a tag, and whatever it shows is
    what Apply posts back -- so it must not show the entry name."""
    doc_of(editor)["background_image"] = yamlio.make_token("image", "screen")

    html = client.get("/node/root/inspect").get_data(as_text=True)
    assert 'name="background_image" value=""' in html
    assert 'value="screen"' not in html


def test_root_background_image_token_survives_an_unrelated_apply(client, editor):
    """Toggling drop_shadow posts the whole form, including a background_image
    box that renders empty for a token. That must not clear the token."""
    doc = doc_of(editor)
    doc["background_image"] = yamlio.make_token("image", "screen")

    client.post("/node/root", data=root_form(drop_shadow="on"))

    assert is_token(doc["background_image"], "image", "screen")
    assert doc["drop_shadow"] is True


def test_root_background_image_token_survives_with_no_picker(tmp_path):
    """A theme with no images: section offers nothing to pick, so the picker
    never renders -- but a token written by hand is still in the document."""
    path = tmp_path / "widgets.yaml"
    path.write_text(SAMPLE.replace("  images:\n    screen: bgcolorlight.jpg\n", ""))
    app = create_app(str(path))
    app.config["TESTING"] = True
    doc = app.config["STATE"].doc
    doc["background_image"] = yamlio.make_token("image", "screen")

    html = app.test_client().get("/node/root/inspect").get_data(as_text=True)
    assert "background_image_token" not in html

    app.test_client().post("/node/root", data=root_form())
    assert is_token(doc["background_image"], "image", "screen")


def test_root_background_image_plain_value_still_round_trips(client, editor):
    doc = doc_of(editor)

    client.post("/node/root", data=root_form(background_image="niagara.jpg"))
    assert doc["background_image"] == "niagara.jpg"

    client.post("/node/root", data=root_form())
    assert "background_image" not in doc


def test_root_background_image_token_replaced_by_a_plain_path(client, editor):
    doc = doc_of(editor)
    doc["background_image"] = yamlio.make_token("image", "screen")

    client.post("/node/root", data=root_form(background_image="niagara.jpg"))
    assert doc["background_image"] == "niagara.jpg"


def test_root_background_image_token_is_saved_as_a_tag(client, editor, tmp_path):
    doc_of(editor)["background_image"] = yamlio.make_token("image", "screen")
    client.post("/save")
    assert "background_image: !image screen" in (tmp_path / "widgets.yaml").read_text()
