"""Non-blocking validation: schema drift + name-reference integrity.

Guiding principle: the schema is advisory, not authoritative. This module
only ever *reports* findings; nothing here can prevent a save.
"""

import jsonschema

from grydgets import theme as theme_mod
from grydgets.editor import schema as schema_mod
from grydgets.editor import tree, yamlio

NAME_REF_FIELDS = schema_mod.NAME_REF_FIELDS


def to_plain(node, sections=None, warnings=None, path="", trail=()):
    """Deep-copy a ruamel doc into plain dict/list/str.

    Two substitutions happen on the way:

    * ``!secret`` becomes a placeholder string. The schema treats those
      fields as plain strings, so this is a sound stand-in for validation.
    * a theme token becomes the value it names, so the document is checked
      as the app will actually build it -- which is what keeps every colour
      and font field in schema.json from having to also accept a token.

    An unresolvable token is reported and left as its literal text rather
    than raising: validation only ever warns, it never blocks a save.
    """
    if yamlio.is_secret(node):
        return "__secret__"
    if yamlio.is_theme_token(node):
        section, name = yamlio.token_parts(node)
        if (section, name) in trail:
            _warn(warnings, path, f"theme token '!{section} {name}' refers to itself")
            return f"!{section} {name}"
        try:
            target = theme_mod.lookup(sections or {}, section, name)
        except theme_mod.ThemeError as e:
            _warn(warnings, path, str(e))
            return f"!{section} {name}"
        return to_plain(target, sections, warnings, path, trail + ((section, name),))
    if isinstance(node, dict):
        return {
            k: to_plain(v, sections, warnings, f"{path}/{k}" if path else str(k), trail)
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [
            to_plain(v, sections, warnings, f"{path}/{i}", trail)
            for i, v in enumerate(node)
        ]
    return node


def _warn(warnings, path, message):
    if warnings is not None:
        warnings.append({"kind": "theme", "path": path or "(root)", "message": message})


def schema_warnings(doc, schema=None):
    if schema is None:
        schema = schema_mod.load_schema()
    theme_issues = []
    plain = to_plain(doc, theme_mod.theme_sections(doc), theme_issues)
    # Defaults are merged into the plain copy, never into the document the
    # editor holds: a node validates against what the theme will give it, but
    # the file keeps saying only what its author wrote.
    theme_mod.apply_defaults(plain)
    validator = jsonschema.Draft7Validator(schema)
    warnings = list(theme_issues)
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
