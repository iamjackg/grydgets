"""Non-blocking validation: schema drift + name-reference integrity.

Guiding principle: the schema is advisory, not authoritative. This module
only ever *reports* findings; nothing here can prevent a save.
"""

import jsonschema

from grydgets.editor import schema as schema_mod
from grydgets.editor import tree, yamlio

NAME_REF_FIELDS = schema_mod.NAME_REF_FIELDS


def to_plain(node):
    """Deep-copy a ruamel doc into plain dict/list/str, replacing !secret
    tagged scalars with a placeholder string (schema treats those fields as
    plain strings, so this is a sound substitution for validation)."""
    if yamlio.is_secret(node):
        return "__secret__"
    if isinstance(node, dict):
        return {k: to_plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [to_plain(v) for v in node]
    return node


def schema_warnings(doc, schema=None):
    if schema is None:
        schema = schema_mod.load_schema()
    plain = to_plain(doc)
    validator = jsonschema.Draft7Validator(schema)
    warnings = []
    for error in validator.iter_errors(plain):
        path = "/".join(str(p) for p in error.absolute_path)
        warnings.append({
            "kind": "schema",
            "path": path or "(root)",
            "message": error.message,
        })
    return warnings


def name_ref_warnings(doc):
    warnings = []
    for path, node in tree.iter_tree(doc):
        children_names = {c.get("name") for c in tree.get_children(node) if c.get("name")}

        default_widget = node.get("default_widget")
        if default_widget and default_widget not in children_names:
            warnings.append({
                "kind": "name-ref",
                "path": path,
                "message": (
                    f"default_widget '{default_widget}' does not match any "
                    f"child name of this {node.get('widget')}"
                ),
            })

        for field_name in ("mapping", "schedule"):
            mapping = node.get(field_name)
            if not isinstance(mapping, dict):
                continue
            for key, value in mapping.items():
                if value and value not in children_names:
                    warnings.append({
                        "kind": "name-ref",
                        "path": path,
                        "message": (
                            f"{field_name} '{key}' -> '{value}' but no child "
                            f"of this {node.get('widget')} is named '{value}'"
                        ),
                    })
    return warnings


def all_warnings(doc, schema=None):
    return schema_warnings(doc, schema) + name_ref_warnings(doc)
