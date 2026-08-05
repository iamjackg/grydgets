"""Flask app factory + routes for the widgets.yaml editor.

Single-user, localhost tool. State lives in one EditorState instance held in
the Flask app config; the in-memory ruamel document is the source of truth
for a session. Save is the only thing that writes to disk.
"""

import argparse
import base64
import copy
import sys
from pathlib import Path

from flask import Flask, render_template, request
from ruamel.yaml import YAMLError
from ruamel.yaml.comments import CommentedSeq

from grydgets import colors, config, rest_fetch, theme as theme_mod
from grydgets.editor import rest_test, schema as schema_mod
from grydgets.editor import secrets_util, theme_ui, tree, validation, yamlio

TESTABLE_WIDGETS = ("rest", "restimage")

ROOT_PATH = "root"

# The screen's own parameters, which the root inspector renders by hand
# rather than from a widget spec -- there is no `widget: screen` node to look
# one up from. Described as fields anyway so they can reuse the ordinary
# controls and the theme-token picker.
BACKGROUND_COLOR_FIELD = schema_mod.FieldSpec(
    "background_color", "color", control="color"
)
BACKGROUND_IMAGE_FIELD = schema_mod.FieldSpec(
    "background_image", "string", control="text"
)
ROOT_FIELDS = (BACKGROUND_IMAGE_FIELD, BACKGROUND_COLOR_FIELD)


class EditorState:
    def __init__(self, widgets_path):
        self.widgets_path = widgets_path
        self.secrets_path = Path(widgets_path).with_name("secrets.yaml")
        self.doc = yamlio.load_doc(widgets_path)
        self.dirty = False
        self.warnings = []
        self.last_backup = None
        self.error = None
        # path -> last parsed JSON response, so the "test request" panel can
        # re-run json_path/jq extraction without hitting the network again.
        self.test_cache = {}

    def reload(self):
        self.doc = yamlio.load_doc(self.widgets_path)
        self.dirty = False
        self.warnings = []
        self.error = None
        self.test_cache = {}

    def mark_dirty(self):
        self.dirty = True


class FieldRow:
    """One field of the inspector, and where its value comes from.

    `source` is None for a value the node sets itself, and otherwise names
    the `theme.defaults` entry supplying it -- a group ("text-like") or a
    widget type. An inherited row is displayed but never applied: it has no
    enabled input on the form, and update_node skips it, so a value the
    theme provides can't be copied into the node just by pressing Apply.
    """

    __slots__ = ("field", "value", "source", "resolved", "token_text")

    def __init__(self, field, value, source=None, resolved=None, token_text=None):
        self.field = field
        self.value = value
        self.source = source
        # What the widget will actually render with: a default written as
        # `!font regular` is shown as the font it resolves to, with the token
        # itself named alongside so the theme entry to edit is still obvious.
        self.resolved = resolved if source is not None else value
        self.token_text = token_text

    @property
    def inherited(self):
        return self.source is not None


def _inherited_value(value, sections):
    """(value the widget gets, token text) for an inherited default."""
    if not yamlio.is_theme_token(value):
        return value, None
    section, name = yamlio.token_parts(value)
    try:
        return theme_mod.lookup(sections, section, name), f"!{section} {name}"
    except theme_mod.ThemeError:
        # An unresolvable token is already reported in the warnings panel;
        # here it just means there is nothing to preview.
        return None, f"!{section} {name}"


def _field_rows(spec, node, defaults=None, sections=None):
    """Fields shown in the edit form: required ones always, optional ones
    only once they're actually present on the node -- otherwise every
    optional field would render as an empty input and get silently written
    back as a default value (false / "" / {}) on every edit, even for fields
    the user never touched. Bringing in a new optional field is what the
    "add property" menu is for.

    A field the node doesn't set but `theme.defaults` does is shown too, as
    an inherited row. Without it the inspector goes quiet about most of what
    a themed widget renders with, and a *required* field supplied by the
    theme would render as an empty input and be written back as "".

    spec is None for widget types not in schema.json (hand-written/legacy
    widgets) -- the schema is advisory, so those nodes still need to be
    viewable/editable, just with no known fields to show here; the
    "unknown fields" raw-YAML path in update_node()/inspector.html covers
    all of their keys instead."""
    if spec is None:
        return []
    defaults = defaults or {}
    rows = []
    for field in spec.fields.values():
        if field.name in node:
            rows.append(FieldRow(field, node[field.name]))
        elif field.name in defaults:
            value, source = defaults[field.name]
            resolved, token_text = _inherited_value(value, sections or {})
            rows.append(FieldRow(field, value, source, resolved, token_text))
        elif field.required:
            rows.append(FieldRow(field, None))
    return rows


def _default_for_control(field):
    if field.control == "checkbox":
        return False
    if field.control == "number":
        return 0
    if field.control in ("raw",):
        return {}
    if field.control == "list":
        return []
    if field.control == "color":
        return [0, 0, 0]
    return ""


def _row_id(path):
    return path.replace("/", "-")


def _parse_number(raw, json_type):
    """Turn a numeric control's text back into an int or a float.

    A whole number stays an int even where the schema says "number". Every
    control hands its value back as a string, and running float() over all of
    them rewrote the file's integer literals on any Apply that touched the
    node -- `transition: 0` became `0.0`, `row_ratios: [4, 1, 4]` became
    `[4.0, 1.0, 4.0]`. Harmless to the widgets, but it churned widgets.yaml
    and buried the real edit in a diff full of noise.
    """
    text = raw.strip()
    if json_type == "integer":
        return int(text)
    try:
        return int(text)
    except ValueError:
        # Genuinely fractional, or exponent notation -- float() owns those.
        return float(text)


def _assign_list(node, name, items):
    """Write a list field without rewriting how it was formatted.

    Assigning a plain Python list drops ruamel's flow-style flag, so
    `providers: [work_calendar]` came back as a two-line block sequence the
    first time anything on the node was applied. Refilling the sequence that
    is already there keeps its style. Comments held against entries past the
    new end are dropped with them -- they belong to items that no longer
    exist, and leaving them behind puts them on the wrong entry.
    """
    existing = node.get(name)
    if not isinstance(existing, CommentedSeq):
        node[name] = items
        return
    existing[:] = items
    comments = getattr(existing.ca, "items", None)
    if comments:
        for index in [i for i in comments if isinstance(i, int) and i >= len(items)]:
            del comments[index]


def _parse_list_value(raw, items_type):
    # One item per line rather than comma-separated: list entries are
    # single-line strings that may legitimately contain commas (e.g. a label
    # "Hello, world"), so splitting on commas would corrupt them on apply.
    items = [v.strip() for v in raw.splitlines() if v.strip() != ""]
    if items_type in ("integer", "number"):
        return [_parse_number(v, items_type) for v in items]
    return items


def _color_is_unchanged(current, submitted):
    """True when `submitted` is the colour `current` already holds.

    Saving a node re-applies every one of its fields, not just the edited
    one, and the colour control only ever hands back four numeric channels.
    Writing those blindly rewrote `'#ff8800'` as `[255, 136, 0, 255]` (and
    `[255, 136, 0]` the same way) whenever anything else on the node
    changed. Comparing the parsed values instead lets a colour nobody
    touched keep whatever form it was written in.
    """
    if current is None:
        return False
    try:
        return colors.parse_color(current) == colors.parse_color(submitted)
    except colors.ColorError:
        # An unparseable existing value is not worth preserving.
        return False


def _parse_color_value(form, field_name):
    parts = []
    for i in range(4):
        v = form.get(f"{field_name}__{i}", "").strip()
        if v == "":
            if i < 3:
                return None
            continue
        try:
            channel = int(v)
        except ValueError:
            return None
        if channel < 0 or channel > 255:
            return None
        parts.append(channel)
    return parts if len(parts) >= 3 else None


def _plain_input_is_blank(form, field):
    """True when the non-token half of a token-capable field was left empty."""
    if field.control == "color":
        return all(form.get(f"{field.name}__{i}", "").strip() == "" for i in range(4))
    return form.get(field.name, "").strip() == ""


def _apply_root_token(node, field, form, field_errors):
    """Handle the theme-token half of one of the screen's fields.

    Returns True when the token half owns the value, so the caller leaves the
    plain control below it alone. The root inspector applies its fields by
    hand rather than through :func:`_apply_field` -- a blank text box there
    means "no background image" and has to remove the key, where the generic
    text branch would write an empty string -- so the token handling the two
    share lives here.
    """
    name = field.name
    current = node.get(name)

    if theme_ui.wants_token(form, name):
        token = theme_ui.parse_token_value(form, name)
        if token is None:
            field_errors[name] = "pick a theme value, or switch back to a plain value"
        elif not theme_ui.same_token(current, token):
            node[name] = token
        return True

    # The plain control renders empty for a token because it has no way to
    # show one, so a blank submission means "left alone" and not "delete it".
    # Checked whether or not the picker was rendered: a theme with no matching
    # section offers no token to pick, but a token written by hand is still
    # sitting in the document and must survive an Apply.
    return yamlio.is_theme_token(current) and _plain_input_is_blank(form, field)


def _apply_field(node, field, form, errors, token_capable=False):
    """Applies the submitted value for `field` to `node`. Returns True if the
    node was actually written/removed, and False if it wasn't -- either an
    error was recorded, or the submitted value is what the node already held.
    Used by update_node() to decide whether to mark the document dirty.

    `token_capable` says the field was rendered with a theme-token picker, so
    the mode radio decides whether the token or the plain control below it
    owns the value.
    """
    name = field.name
    current = node.get(name)

    if token_capable:
        if theme_ui.wants_token(form, name):
            token = theme_ui.parse_token_value(form, name)
            if token is None:
                errors.append((name, "pick a theme value, or switch back to a plain value"))
                return False
            if theme_ui.same_token(current, token):
                return False
            node[name] = token
            return True
        if yamlio.is_theme_token(current) and _plain_input_is_blank(form, field):
            # The radio moved off "theme" with nothing typed in its place.
            # The plain control renders empty for a token (it has no way to
            # show one), so applying here would write "" over the token or,
            # for a number, drop the key outright. A stray radio click
            # shouldn't cost the value.
            errors.append(
                (name, "enter a value to replace the theme token, or leave this set to 'theme'")
            )
            return False

    if field.control == "checkbox":
        node[name] = form.get(name) == "on"
        return True
    elif field.control == "number":
        raw = form.get(name, "").strip()
        if raw == "":
            node.pop(name, None)
            return True
        try:
            node[name] = _parse_number(raw, field.json_type)
        except ValueError:
            errors.append((name, f"'{raw}' is not a valid number"))
            return False
        return True
    elif field.control == "color":
        color = _parse_color_value(form, name)
        if color is None:
            errors.append((name, "a color needs at least r, g, b"))
            return False
        if _color_is_unchanged(current, color):
            return False
        node[name] = color
        return True
    elif field.control == "select":
        node[name] = form.get(name, "")
        return True
    elif field.control == "list":
        try:
            items = _parse_list_value(form.get(name, ""), field.items_type)
        except ValueError:
            errors.append((name, "invalid list value"))
            return False
        _assign_list(node, name, items)
        return True
    elif field.control in ("raw", "textarea"):
        raw = form.get(name, "")
        if field.control == "textarea":
            node[name] = raw
            return True
        try:
            node[name] = yamlio.parse_value(raw) if raw.strip() else {}
        except YAMLError as exc:
            errors.append((name, f"invalid YAML: {exc}"))
            return False
        return True
    else:
        node[name] = form.get(name, "")
        return True


def _assign_mapping(node, name, values):
    """Write a mapping field by updating the mapping already in place.

    Replacing it with a fresh dict throws away everything ruamel hangs off
    the old one -- inline comments, and the blank lines that separate a
    block from the key after it. Keys that go away lose theirs, which is
    right: the comment belonged to them.
    """
    existing = node.get(name)
    if not isinstance(existing, dict):
        node[name] = values
        return
    for key in list(existing.keys()):
        if key not in values:
            del existing[key]
    for key, value in values.items():
        if isinstance(value, dict):
            _assign_mapping(existing, key, value)
        else:
            existing[key] = value


def _apply_name_ref_field(node, field_name, kind, form, errors):
    if kind == "single":
        value = form.get(field_name, "").strip()
        if value:
            node[field_name] = value
        else:
            node.pop(field_name, None)
    else:  # "values": dict field, parallel key/val lists
        keys = form.getlist(f"{field_name}_key")
        vals = form.getlist(f"{field_name}_val")
        result = {}
        for k, v in zip(keys, vals):
            k = k.strip()
            if k and v:
                result[k] = v
        if not result:
            node.pop(field_name, None)
            return
        _assign_mapping(node, field_name, result)


def _parse_secret_capable_value(form, prefix):
    """A field rendered by the secret_capable_field macro: either a plain
    string or a !secret reference, chosen via a radio at `{prefix}_kind`."""
    if form.get(f"{prefix}_kind") == "secret":
        key = form.get(f"{prefix}_secret_key", "").strip()
        return yamlio.make_secret(key) if key else None
    value = form.get(f"{prefix}_plain_value", "").strip()
    return value or None


def _apply_secret_capable_field(node, field_name, form, prefix=None):
    value = _parse_secret_capable_value(form, prefix or field_name)
    if value is not None:
        node[field_name] = value
    else:
        node.pop(field_name, None)


def _apply_auth_field(node, form):
    auth_type = form.get("auth_type", "bearer")
    if auth_type == "bearer":
        bearer = _parse_secret_capable_value(form, "auth_bearer")
        auth = {"bearer": bearer} if bearer is not None else {}
    else:
        username = _parse_secret_capable_value(form, "auth_username")
        password = _parse_secret_capable_value(form, "auth_password")
        basic = {}
        if username is not None:
            basic["username"] = username
        if password is not None:
            basic["password"] = password
        auth = {"basic": basic} if basic else {}
    if not auth:
        node.pop("auth", None)
        return
    _assign_mapping(node, "auth", auth)


def _token_is_read_only(field, value, token_capable):
    """True when a field holds a theme token that no control on the form can
    hand back intact, so update_node must leave it alone.

    Two controls can round-trip a token: the picker a token-capable field is
    rendered with, and the raw YAML box, whose contents are parsed back
    through ruamel and keep their tag. Every other control -- text, number,
    select, checkbox, list -- can only produce a literal, so applying one
    would flatten `!font bold` to the string `bold`, or (a number input
    can't display `radius`, so it posts empty) drop the key entirely.
    """
    if not yamlio.contains_theme_token(value):
        return False
    if field.control == "raw":
        return False
    return not (token_capable and yamlio.is_theme_token(value))


def _color_channels_filter(value):
    """Expand a colour value into the four r/g/b/a numbers the colour control
    shows.

    Colours may be written as a hex string in widgets.yaml. The control edits
    them as four numeric channels, and indexing a string yields its characters
    -- '#ff8800' would fill the boxes with '#', 'f', 'f', '8' and write that
    back on the next Apply. Parsing here keeps the control on numbers whatever
    form the file uses. Note the editor still *saves* a list, so applying this
    field to a hex colour rewrites it as [r, g, b, a].
    """
    if value is None:
        return []
    try:
        return list(colors.parse_color(value))
    except colors.ColorError:
        # Not a colour we understand: leave the boxes empty rather than
        # guessing, so a bad value stays visible instead of being overwritten.
        return []


def _to_yaml_filter(value):
    if value is None:
        return ""
    # ruamel's own dumper, not pyyaml: ruamel's scalar-string subtypes
    # (DoubleQuotedScalarString etc, used throughout widgets.yaml) aren't
    # representable by plain pyyaml.
    return yamlio.dump_value_to_string(value)


def create_app(widgets_path):
    app = Flask(__name__)
    state = EditorState(widgets_path)
    app.config["STATE"] = state

    app.jinja_env.filters["to_yaml"] = _to_yaml_filter
    app.jinja_env.filters["color_channels"] = _color_channels_filter
    app.jinja_env.globals.update(
        get_widget_spec=schema_mod.get_widget_spec,
        get_widget_types=schema_mod.get_widget_types,
        is_secret=yamlio.is_secret,
        contains_secret=yamlio.contains_secret,
        secret_display=yamlio.secret_display,
        is_theme_token=yamlio.is_theme_token,
        contains_theme_token=yamlio.contains_theme_token,
        token_display=yamlio.token_display,
        # Shared with update_node so the field the inspector draws read-only
        # is exactly the field the apply loop skips.
        token_is_read_only=_token_is_read_only,
        color_channels=_color_channels_filter,
        dump_value=yamlio.dump_value_to_string,
        child_path=tree.child_path,
        row_id=_row_id,
        ROOT_PATH=ROOT_PATH,
    )

    def render_root_inspector(path, node, field_errors=None):
        return render_template(
            "inspector_root.html",
            node=node,
            path=path,
            widgets_path=state.widgets_path,
            # Keyed by field name, the same shape the widget inspector gets,
            # so a field with no matching theme section simply has no picker.
            token_options={
                field.name: theme_ui.token_options(state.doc, field)
                for field in ROOT_FIELDS
            },
            field_errors=field_errors or {},
        )

    def node_defaults(node):
        """The theme.defaults entries that apply to a node's widget type,
        each paired with the entry name it came from."""
        return theme_mod.defaults_with_source(state.doc.get("theme")).get(
            node.get("widget"), {}
        )

    def render_inspector(path, node, field_errors=None):
        """The inspector pane for one widget node. Five routes render it
        (inspect / update / add-field / remove-field / override-field) and
        every one of them needs the same context: token pickers, and the
        fields the theme is supplying."""
        widget_type = node.get("widget")
        spec = schema_mod.get_widget_spec(widget_type)
        defaults = node_defaults(node)
        rows = _field_rows(
            spec, node, defaults, theme_mod.theme_sections(state.doc)
        )
        return render_template(
            "inspector.html",
            node=node,
            path=path,
            widget_type=widget_type,
            spec=spec,
            field_rows=rows,
            # Names the theme could supply, so an overridden field's "remove"
            # button can say what removing it falls back to, and the "add
            # property" menu can leave out what is already on screen.
            default_sources={name: source for name, (_v, source) in defaults.items()},
            inherited_names=[row.field.name for row in rows if row.inherited],
            siblings=tree.get_children(node),
            name_ref_fields=schema_mod.NAME_REF_FIELDS,
            raw_textarea_fields=schema_mod.RAW_TEXTAREA_FIELDS,
            secret_keys=secrets_util.list_secret_keys(state.secrets_path),
            token_options=theme_ui.options_by_field(state.doc, spec),
            field_errors=field_errors or {},
        )

    def render_node_fragment(path, oob=False):
        node = _get_node_or_root(state.doc, path)
        return render_template("tree_node.html", node=node, path=path, oob=oob)

    def render_row_main_oob(path):
        """OOB-swap just a node's label (name/badges) after a non-structural
        edit -- leaves the surrounding <details> untouched so its open/collapsed
        state (and that of its descendants) survives the edit."""
        node = _get_node_or_root(state.doc, path)
        return render_template("_row_main.html", node=node, path=path, oob=True)

    def render_root_list_fragment():
        return render_template(
            "root_list.html",
            widgets=state.doc.get("widgets") or [],
        )

    def render_dirty_badge(oob=False):
        return render_template("dirty_badge.html", dirty=state.dirty, oob=oob)

    def render_warnings_panel():
        return render_template("warnings_panel.html", warnings=state.warnings)

    def refresh_warnings_oob():
        state.warnings = validation.all_warnings(state.doc)
        return _oob(render_warnings_panel(), "warnings")

    def _get_node_or_root(doc, path):
        if path == ROOT_PATH:
            return doc
        return tree.get_node(doc, path)

    def _oob(html, elem_id):
        return f'<div id="{elem_id}" hx-swap-oob="true">{html}</div>'

    def render_subtree_oob(parent_path):
        """Re-render whichever container holds a given node's siblings, as an
        OOB fragment: the parent node's own <details>/<div> (self-contained,
        already carries a matching id) or the top-level widgets list (no
        self id of its own, so it needs the generic wrapper)."""
        if parent_path is None:
            return _oob(render_root_list_fragment(), "tree-root-list")
        return render_node_fragment(parent_path, oob=True)

    @app.route("/")
    def index():
        return render_template(
            "base.html",
            widgets=state.doc.get("widgets") or [],
            dirty=state.dirty,
            warnings=state.warnings,
            widgets_path=state.widgets_path,
        )

    @app.route("/node/<path:path>/inspect")
    def inspect(path):
        node = _get_node_or_root(state.doc, path)
        if path == ROOT_PATH:
            return render_root_inspector(path, node)

        return render_inspector(path, node)

    @app.route("/node/<path:path>", methods=["POST"])
    def update_node(path):
        node = _get_node_or_root(state.doc, path)
        form = request.form
        errors = []

        if path == ROOT_PATH:
            field_errors = {}

            if not _apply_root_token(node, BACKGROUND_IMAGE_FIELD, form, field_errors):
                bg = form.get("background_image", "").strip()
                if bg:
                    node["background_image"] = bg
                else:
                    node.pop("background_image", None)

            node["drop_shadow"] = form.get("drop_shadow") == "on"

            if not _apply_root_token(node, BACKGROUND_COLOR_FIELD, form, field_errors):
                current_bg = node.get("background_color")
                if _plain_input_is_blank(form, BACKGROUND_COLOR_FIELD):
                    node.pop("background_color", None)
                else:
                    color = _parse_color_value(form, "background_color")
                    if color is None:
                        field_errors["background_color"] = (
                            "a color needs at least r, g, b"
                        )
                    elif not _color_is_unchanged(current_bg, color):
                        node["background_color"] = color

            state.mark_dirty()
            return (
                render_root_inspector(path, node, field_errors)
                + render_dirty_badge(oob=True)
                + refresh_warnings_oob()
            )

        widget_type = node.get("widget")
        spec = schema_mod.get_widget_spec(widget_type)
        changed = False

        new_name = form.get("name", "").strip() or None
        if new_name != node.get("name"):
            changed = True
        if new_name:
            node["name"] = new_name
        else:
            node.pop("name", None)

        token_fields = theme_ui.options_by_field(state.doc, spec)
        for row in _field_rows(spec, node, node_defaults(node)):
            if row.inherited:
                # The theme supplies this one. Its controls are rendered
                # disabled, so the browser posts nothing for it -- and if one
                # ever did, writing it would copy the theme's value onto the
                # node and quietly turn it into an override. Overriding is
                # what the override-field route is for.
                continue
            field = row.field
            value = node.get(field.name)
            token_capable = field.name in token_fields
            if field.name == "auth":
                _apply_auth_field(node, form)
                changed = True
            elif yamlio.is_secret(value):
                _apply_secret_capable_field(node, field.name, form)
                changed = True
            elif yamlio.contains_secret(value):
                continue  # secret nested somewhere other than auth -- read-only
            elif _token_is_read_only(field, value, token_capable):
                continue  # theme token this form can't carry -- read-only
            elif field.name in schema_mod.NAME_REF_FIELDS:
                _apply_name_ref_field(
                    node, field.name, schema_mod.NAME_REF_FIELDS[field.name], form, errors
                )
                changed = True
            else:
                if _apply_field(node, field, form, errors, token_capable=token_capable):
                    changed = True

        # unknown fields present on the node but not in the schema: raw round-trip
        # (when spec is None -- widget type unknown to schema.json -- every
        # field on the node falls into this path)
        known = (set(spec.fields.keys()) if spec else set()) | {"widget", "name", "children"}
        for key in list(node.keys()):
            if key in known:
                continue
            value = node.get(key)
            if yamlio.is_secret(value):
                _apply_secret_capable_field(node, key, form, prefix=f"unknown__{key}")
                changed = True
                continue
            if yamlio.contains_secret(value):
                continue
            form_key = f"unknown__{key}"
            if form_key in form:
                raw = form.get(form_key, "")
                try:
                    # parse_value, not pyyaml: an unknown field is free to hold
                    # a theme token, and only the round-trip loader gives it
                    # back as a tag rather than refusing the whole box.
                    node[key] = yamlio.parse_value(raw) if raw.strip() else None
                    changed = True
                except YAMLError as exc:
                    errors.append((key, f"invalid YAML: {exc}"))

        if changed:
            state.mark_dirty()
        return (
            render_inspector(path, node, dict(errors))
            + render_row_main_oob(path)
            + render_dirty_badge(oob=True)
            + refresh_warnings_oob()
        )

    @app.route("/node/<path:path>/add-child-form")
    def add_child_form(path):
        return render_template(
            "add_child_form.html", path=path, widget_types=schema_mod.get_widget_types()
        )

    @app.route("/node/<path:path>/children", methods=["POST"])
    def add_child(path):
        widget_type = request.form.get("widget_type")
        name = request.form.get("name", "").strip()

        parent_path = None if path == ROOT_PATH else path
        if parent_path is not None:
            parent_node = tree.get_node(state.doc, parent_path)
            parent_spec = schema_mod.get_widget_spec(parent_node.get("widget"))
            current_count = len(tree.get_children(parent_node))
            if (
                parent_spec
                and parent_spec.max_children is not None
                and current_count >= parent_spec.max_children
            ):
                return (
                    f'<div class="save-status error">'
                    f"'{parent_node.get('widget')}' allows at most {parent_spec.max_children} "
                    f"child(ren) -- already has {current_count}.</div>"
                )

        new_node = {"widget": widget_type}
        if name:
            new_node["name"] = name

        tree.add_child(state.doc, parent_path, new_node)
        state.mark_dirty()

        return (
            render_subtree_oob(parent_path)
            + render_dirty_badge(oob=True)
            + refresh_warnings_oob()
        )

    @app.route("/node/<path:path>", methods=["DELETE"])
    def delete_node(path):
        parent_path = tree.get_parent_path(path)
        tree.delete_node(state.doc, path)
        state.mark_dirty()

        return (
            render_subtree_oob(parent_path)
            + render_dirty_badge(oob=True)
            + _oob('<div class="placeholder">Select a node to edit.</div>', "inspector")
            + refresh_warnings_oob()
        )

    @app.route("/node/<path:path>/move", methods=["POST"])
    def move_node(path):
        direction = request.form.get("direction")
        segments = tree.parse_path(path)
        current_index = segments[-1][1]
        delta = -1 if direction == "up" else 1
        new_path = tree.move_node(state.doc, path, current_index + delta)
        state.mark_dirty()

        parent_path = tree.get_parent_path(new_path)
        return (
            render_subtree_oob(parent_path)
            + render_dirty_badge(oob=True)
            + _oob('<div class="placeholder">Select a node to edit.</div>', "inspector")
            + refresh_warnings_oob()
        )

    @app.route("/node/<path:path>/add-field", methods=["POST"])
    def add_field(path):
        node = tree.get_node(state.doc, path)
        widget_type = node.get("widget")
        spec = schema_mod.get_widget_spec(widget_type)
        field_name = request.form.get("field_name")
        field = spec.fields.get(field_name)
        if field is not None and field_name not in node:
            node[field_name] = _default_for_control(field)
            state.mark_dirty()

        return (
            render_inspector(path, node)
            + render_dirty_badge(oob=True)
            + refresh_warnings_oob()
        )

    @app.route("/node/<path:path>/override-field", methods=["POST"])
    def override_field(path):
        """Copy a value the theme is supplying onto the node, so it can be
        edited there. Removing the field again drops back to the theme."""
        node = tree.get_node(state.doc, path)
        field_name = request.form.get("field_name")
        defaults = node_defaults(node)
        if field_name in defaults and field_name not in node:
            value, _source = defaults[field_name]
            # Deep copy for the reason theme._apply_defaults documents: two
            # nodes overriding the same entry would otherwise share one
            # mutable list, and editing either would edit both.
            node[field_name] = copy.deepcopy(value)
            state.mark_dirty()

        return (
            render_inspector(path, node)
            + render_dirty_badge(oob=True)
            + refresh_warnings_oob()
        )

    @app.route("/node/<path:path>/field/<field_name>", methods=["DELETE"])
    def remove_field(path, field_name):
        node = tree.get_node(state.doc, path)
        widget_type = node.get("widget")
        spec = schema_mod.get_widget_spec(widget_type)
        field = spec.fields.get(field_name) if spec else None
        removable = field_name not in ("widget", "name", "children") and (
            field is None or not field.required
        )
        if removable and field_name in node:
            node.pop(field_name, None)
            state.mark_dirty()

        return (
            render_inspector(path, node)
            + render_dirty_badge(oob=True)
            + refresh_warnings_oob()
        )

    @app.route("/node/<path:path>/test", methods=["POST"])
    def test_node(path):
        """Actually run a rest/restimage widget's request and show the result.

        Live network call: for a POST/PUT/PATCH widget this sends the real
        request to the endpoint (the panel warns about that). Secrets are
        resolved server-side to make the call but never rendered."""
        node = tree.get_node(state.doc, path)
        widget_type = node.get("widget")
        if widget_type not in TESTABLE_WIDGETS:
            return (
                f'<div class="test-error">\'{widget_type}\' widgets can\'t be '
                f"tested here.</div>"
            )

        # Tested with the theme's defaults filled in and its tokens resolved,
        # so a node whose url or auth comes from the theme tests the way it
        # renders rather than as an empty request.
        sections = theme_mod.theme_sections(state.doc)
        defaults = node_defaults(node)

        if widget_type == "restimage":
            summary, result = rest_test.test_image(
                node, str(state.secrets_path), sections, defaults
            )
            state.test_cache.pop(path, None)
            image_data_uri = None
            if result.image_bytes is not None:
                mime = result.content_type or "image/png"
                if not mime.startswith("image/"):
                    mime = "image/png"
                encoded = base64.b64encode(result.image_bytes).decode()
                image_data_uri = f"data:{mime};base64,{encoded}"
            return render_template(
                "test_panel_image.html",
                path=path,
                summary=summary,
                result=result,
                image_data_uri=image_data_uri,
                image_size=len(result.image_bytes) if result.image_bytes else 0,
            )

        summary, result = rest_test.test_rest(
            node, str(state.secrets_path), sections, defaults
        )
        can_extract = result.json is not None
        if can_extract:
            state.test_cache[path] = result.json
        else:
            state.test_cache.pop(path, None)
        return render_template(
            "test_panel_rest.html",
            path=path,
            summary=summary,
            result=result,
            node=node,
            can_extract=can_extract,
        )

    @app.route("/node/<path:path>/test/extract", methods=["POST"])
    def test_extract(path):
        """Re-run just json_path/jq/format extraction against the response
        cached by the last /test call -- no new network request. Lets the user
        iterate on the extraction against real data."""
        cached = state.test_cache.get(path)
        json_path = request.form.get("json_path", "").strip() or None
        jq_expression = request.form.get("jq_expression", "").strip() or None
        format_string = request.form.get("format_string", "") or "{}"
        if cached is None:
            return render_template("extraction_output.html", stale=True)
        value, extracted, error = rest_fetch.apply_extraction(
            cached, json_path, jq_expression, format_string
        )
        return render_template(
            "extraction_output.html",
            stale=False,
            value=value,
            extracted=extracted,
            extraction_error=error,
        )

    @app.route("/save", methods=["POST"])
    def save():
        state.warnings = validation.all_warnings(state.doc)
        try:
            backup = yamlio.save_doc(state.doc, state.widgets_path)
            state.last_backup = backup
            state.dirty = False
            state.error = None
            status_html = render_template(
                "save_status.html", ok=True, backup=backup, error=None
            )
        except (OSError, YAMLError) as exc:
            state.error = str(exc)
            status_html = render_template("save_status.html", ok=False, backup=None, error=exc)

        return (
            status_html
            + _oob(render_warnings_panel(), "warnings")
            + render_dirty_badge(oob=True)
        )

    @app.route("/reload", methods=["POST"])
    def reload_doc():
        state.reload()
        response = render_template("save_status.html", ok=True, backup=None, error=None, reloaded=True)
        headers = {"HX-Refresh": "true"}
        return response, 200, headers

    @app.route("/raw")
    def raw():
        content = yamlio.dump_doc_to_string(state.doc)
        return render_template("raw.html", content=content, widgets_path=state.widgets_path)

    return app


def main():
    parser = argparse.ArgumentParser(description="Local editor for widgets.yaml")
    parser.add_argument(
        "--widgets", default="widgets.yaml", metavar="FILE",
        help="Widget configuration file to edit (default: widgets.yaml)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    # A file that can't be read is the user's, not a bug, so it gets the
    # message on its own -- the same treatment main.py gives conf.yaml.
    try:
        app = create_app(args.widgets)
    except OSError as e:
        sys.exit(
            f"grydgets-editor: {config.describe_read_failure(args.widgets, e)}"
        )
    except YAMLError as e:
        sys.exit(f"grydgets-editor: {args.widgets} is not valid YAML:\n{e}")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
