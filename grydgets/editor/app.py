"""Flask app factory + routes for the widgets.yaml editor.

Single-user, localhost tool. State lives in one EditorState instance held in
the Flask app config; the in-memory ruamel document is the source of truth
for a session. Save is the only thing that writes to disk.
"""

import argparse
import base64
from pathlib import Path

import yaml as pyyaml
from flask import Flask, render_template, request
from ruamel.yaml import YAMLError

from grydgets import colors, rest_fetch
from grydgets.editor import rest_test, schema as schema_mod
from grydgets.editor import secrets_util, tree, validation, yamlio

TESTABLE_WIDGETS = ("rest", "restimage")

ROOT_PATH = "root"


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


def _visible_fields(spec, node):
    """Fields shown in (and applied from) the edit form: required ones always,
    optional ones only once they're actually present on the node -- otherwise
    every optional field would render as an empty input and get silently
    written back as a default value (false / "" / {}) on every edit, even
    for fields the user never touched. Bringing in a new optional field is
    what the "add property" menu is for.

    spec is None for widget types not in schema.json (hand-written/legacy
    widgets) -- the schema is advisory, so those nodes still need to be
    viewable/editable, just with no known fields to show here; the
    "unknown fields" raw-YAML path in update_node()/inspector.html covers
    all of their keys instead."""
    if spec is None:
        return []
    return [f for f in spec.fields.values() if f.required or f.name in node]


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


def _parse_list_value(raw, items_type):
    # One item per line rather than comma-separated: list entries are
    # single-line strings that may legitimately contain commas (e.g. a label
    # "Hello, world"), so splitting on commas would corrupt them on apply.
    items = [v.strip() for v in raw.splitlines() if v.strip() != ""]
    if items_type == "integer":
        return [int(v) for v in items]
    if items_type == "number":
        return [float(v) for v in items]
    return items


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


def _apply_field(node, field, form, errors):
    """Applies the submitted value for `field` to `node`. Returns True if the
    node was actually written/removed, False if an error was recorded instead
    (nothing changed) -- used by update_node() to decide whether to mark the
    document dirty."""
    name = field.name
    if field.control == "checkbox":
        node[name] = form.get(name) == "on"
        return True
    elif field.control == "number":
        raw = form.get(name, "").strip()
        if raw == "":
            node.pop(name, None)
            return True
        try:
            node[name] = int(raw) if field.json_type == "integer" else float(raw)
        except ValueError:
            errors.append((name, f"'{raw}' is not a valid number"))
            return False
        return True
    elif field.control == "color":
        color = _parse_color_value(form, name)
        if color is None:
            errors.append((name, "a color needs at least r, g, b"))
            return False
        node[name] = color
        return True
    elif field.control == "select":
        node[name] = form.get(name, "")
        return True
    elif field.control == "list":
        try:
            node[name] = _parse_list_value(form.get(name, ""), field.items_type)
        except ValueError:
            errors.append((name, "invalid list value"))
            return False
        return True
    elif field.control in ("raw", "textarea"):
        raw = form.get(name, "")
        if field.control == "textarea":
            node[name] = raw
            return True
        try:
            node[name] = pyyaml.safe_load(raw) if raw.strip() else {}
        except pyyaml.YAMLError as exc:
            errors.append((name, f"invalid YAML: {exc}"))
            return False
        return True
    else:
        node[name] = form.get(name, "")
        return True


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
        existing = node.get(field_name)
        if isinstance(existing, dict):
            # Mutate the existing mapping in place rather than replacing it with
            # a fresh dict, so ruamel keeps any inline comments attached to keys
            # that survive the edit. Renamed/removed keys naturally lose theirs.
            for k in list(existing.keys()):
                if k not in result:
                    del existing[k]
            for k, v in result.items():
                existing[k] = v
        else:
            node[field_name] = result


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
        node["auth"] = {"bearer": bearer} if bearer is not None else {}
    else:
        username = _parse_secret_capable_value(form, "auth_username")
        password = _parse_secret_capable_value(form, "auth_password")
        basic = {}
        if username is not None:
            basic["username"] = username
        if password is not None:
            basic["password"] = password
        node["auth"] = {"basic": basic} if basic else {}
    if not node["auth"]:
        node.pop("auth", None)


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
        dump_value=yamlio.dump_value_to_string,
        child_path=tree.child_path,
        row_id=_row_id,
        visible_fields=_visible_fields,
        ROOT_PATH=ROOT_PATH,
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
            return render_template(
                "inspector_root.html",
                node=node,
                path=path,
                widgets_path=state.widgets_path,
                field_errors={},
            )

        widget_type = node.get("widget")
        spec = schema_mod.get_widget_spec(widget_type)
        siblings = tree.get_children(node)
        return render_template(
            "inspector.html",
            node=node,
            path=path,
            widget_type=widget_type,
            spec=spec,
            siblings=siblings,
            name_ref_fields=schema_mod.NAME_REF_FIELDS,
            raw_textarea_fields=schema_mod.RAW_TEXTAREA_FIELDS,
            secret_keys=secrets_util.list_secret_keys(state.secrets_path),
            field_errors={},
        )

    @app.route("/node/<path:path>", methods=["POST"])
    def update_node(path):
        node = _get_node_or_root(state.doc, path)
        form = request.form
        errors = []

        if path == ROOT_PATH:
            bg = form.get("background_image", "").strip()
            if bg:
                node["background_image"] = bg
            else:
                node.pop("background_image", None)
            node["drop_shadow"] = form.get("drop_shadow") == "on"

            field_errors = {}
            channels_blank = all(
                form.get(f"background_color__{i}", "").strip() == "" for i in range(4)
            )
            if channels_blank:
                node.pop("background_color", None)
            else:
                color = _parse_color_value(form, "background_color")
                if color is not None:
                    node["background_color"] = color
                else:
                    field_errors["background_color"] = "a color needs at least r, g, b"

            state.mark_dirty()
            return (
                render_template(
                    "inspector_root.html",
                    node=node,
                    path=path,
                    widgets_path=state.widgets_path,
                    field_errors=field_errors,
                )
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

        for field in _visible_fields(spec, node):
            value = node.get(field.name)
            if field.name == "auth":
                _apply_auth_field(node, form)
                changed = True
            elif yamlio.is_secret(value):
                _apply_secret_capable_field(node, field.name, form)
                changed = True
            elif yamlio.contains_secret(value):
                continue  # secret nested somewhere other than auth -- read-only
            elif field.name in schema_mod.NAME_REF_FIELDS:
                _apply_name_ref_field(
                    node, field.name, schema_mod.NAME_REF_FIELDS[field.name], form, errors
                )
                changed = True
            else:
                if _apply_field(node, field, form, errors):
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
                    node[key] = pyyaml.safe_load(raw) if raw.strip() else None
                    changed = True
                except pyyaml.YAMLError as exc:
                    errors.append((key, f"invalid YAML: {exc}"))

        if changed:
            state.mark_dirty()
        siblings = tree.get_children(node)
        inspector_html = render_template(
            "inspector.html",
            node=node,
            path=path,
            widget_type=widget_type,
            spec=spec,
            siblings=siblings,
            name_ref_fields=schema_mod.NAME_REF_FIELDS,
            raw_textarea_fields=schema_mod.RAW_TEXTAREA_FIELDS,
            secret_keys=secrets_util.list_secret_keys(state.secrets_path),
            field_errors=dict(errors),
        )
        return (
            inspector_html
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

        siblings = tree.get_children(node)
        inspector_html = render_template(
            "inspector.html",
            node=node,
            path=path,
            widget_type=widget_type,
            spec=spec,
            siblings=siblings,
            name_ref_fields=schema_mod.NAME_REF_FIELDS,
            raw_textarea_fields=schema_mod.RAW_TEXTAREA_FIELDS,
            secret_keys=secrets_util.list_secret_keys(state.secrets_path),
            field_errors={},
        )
        return inspector_html + render_dirty_badge(oob=True) + refresh_warnings_oob()

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

        siblings = tree.get_children(node)
        inspector_html = render_template(
            "inspector.html",
            node=node,
            path=path,
            widget_type=widget_type,
            spec=spec,
            siblings=siblings,
            name_ref_fields=schema_mod.NAME_REF_FIELDS,
            raw_textarea_fields=schema_mod.RAW_TEXTAREA_FIELDS,
            secret_keys=secrets_util.list_secret_keys(state.secrets_path),
            field_errors={},
        )
        return inspector_html + render_dirty_badge(oob=True) + refresh_warnings_oob()

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

        if widget_type == "restimage":
            summary, result = rest_test.test_image(node, str(state.secrets_path))
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

        summary, result = rest_test.test_rest(node, str(state.secrets_path))
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

    app = create_app(args.widgets)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
