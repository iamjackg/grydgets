"""Parse schema.json into per-widget-type field specs for form generation.

The schema is advisory, not authoritative (validation warns, it never
blocks) -- this module only *reads* schema.json to drive UI generation and
later validation; it never mutates it.
"""

import json
from pathlib import Path

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schema.json"

# Fields that are technically JSON-schema strings/objects but are gnarly
# enough (jq/jinja templates, arbitrary payload bodies) that a plain text
# input or generic object form would be unusable.
RAW_TEXTAREA_FIELDS = {
    "jq_expression",
    "labels_jq_expression",
    "template",
}

# Fields whose values reference a sibling child's `name`. Not expressible in
# JSON Schema itself -- this is domain knowledge from the widget classes.
NAME_REF_FIELDS = {
    "default_widget": "single",  # value is one child name
    "mapping": "values",  # dict values are child names, keys are free text
    "schedule": "values",  # dict values are child names, keys are HH:MM
}

COLOR_REF = "#/definitions/color"
AUTH_REF = "#/definitions/auth_scheme"


class FieldSpec:
    def __init__(self, name, json_type=None, control="text", enum=None,
                 minimum=None, maximum=None, required=False, items_type=None):
        self.name = name
        self.json_type = json_type
        self.control = control
        self.enum = enum
        self.minimum = minimum
        self.maximum = maximum
        self.required = required
        self.items_type = items_type

    def to_dict(self):
        return {
            "name": self.name,
            "json_type": self.json_type,
            "control": self.control,
            "enum": self.enum,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "required": self.required,
            "items_type": self.items_type,
        }


class WidgetSpec:
    def __init__(self, widget_type):
        self.widget_type = widget_type
        self.fields = {}  # name -> FieldSpec, excludes "widget"/"name"/"children"
        self.min_children = 0
        self.max_children = 0  # 0 means "not a container"
        self.has_children_field = False

    def is_container(self):
        return self.has_children_field

    def optional_fields(self):
        return [f for f in self.fields.values() if not f.required]


def _field_spec(name, prop, required_names):
    ref = prop.get("$ref")
    if ref == COLOR_REF:
        return FieldSpec(name, "color", control="color", required=name in required_names)
    if ref == AUTH_REF:
        return FieldSpec(name, "object", control="raw", required=name in required_names)

    json_type = prop.get("type")
    enum = prop.get("enum")

    if name in RAW_TEXTAREA_FIELDS:
        control = "textarea"
    elif json_type == "boolean":
        control = "checkbox"
    elif enum:
        control = "select"
    elif json_type in ("integer", "number"):
        control = "number"
    elif json_type == "object":
        control = "raw"
    elif json_type == "array":
        items = prop.get("items", {})
        if items.get("$ref") == COLOR_REF or items.get("type") == "object":
            control = "raw"
        else:
            control = "list"
    else:
        control = "text"

    items_type = None
    if json_type == "array":
        items_type = prop.get("items", {}).get("type")

    return FieldSpec(
        name,
        json_type=json_type,
        control=control,
        enum=enum,
        minimum=prop.get("minimum"),
        maximum=prop.get("maximum"),
        required=name in required_names,
        items_type=items_type,
    )


def load_schema(schema_path=DEFAULT_SCHEMA_PATH):
    with open(schema_path) as f:
        return json.load(f)


def parse_widget_specs(schema=None):
    """Return (widget_types, {widget_type: WidgetSpec})."""
    if schema is None:
        schema = load_schema()

    widget_def = schema["definitions"]["widget"]
    widget_types = list(widget_def["properties"]["widget"]["enum"])
    specs = {}

    for branch in widget_def["allOf"]:
        widget_type = branch["if"]["properties"]["widget"]["const"]
        then = branch["then"]
        required_names = set(then.get("required", []))
        properties = then.get("properties", {})

        spec = WidgetSpec(widget_type)
        for name, prop in properties.items():
            if name in ("widget", "name"):
                continue
            if name == "children":
                spec.has_children_field = True
                spec.min_children = prop.get("minItems", 0)
                spec.max_children = prop.get("maxItems")  # None means unbounded
                continue
            spec.fields[name] = _field_spec(name, prop, required_names)

        specs[widget_type] = spec

    # Widget types present in the enum but with no allOf branch (shouldn't
    # happen today, but don't silently drop them from the type picker).
    for widget_type in widget_types:
        if widget_type not in specs:
            specs[widget_type] = WidgetSpec(widget_type)

    return widget_types, specs


_widget_types = None
_widget_specs = None


def get_widget_types():
    _ensure_loaded()
    return _widget_types


def get_widget_specs():
    _ensure_loaded()
    return _widget_specs


def get_widget_spec(widget_type):
    _ensure_loaded()
    return _widget_specs.get(widget_type)


def _ensure_loaded():
    global _widget_types, _widget_specs
    if _widget_specs is None:
        _widget_types, _widget_specs = parse_widget_specs()


def reload():
    """Force a re-parse of schema.json (used by tests / hot editing of the schema)."""
    global _widget_types, _widget_specs
    _widget_types, _widget_specs = parse_widget_specs()
