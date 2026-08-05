"""Theme tokens and per-widget defaults for widgets.yaml.

A ``theme:`` block names values once and hands them out by reference::

    theme:
      colors:
        panel: '#3b4252'
        text: '#eceff4'
      fonts:
        regular: fonts/Inter-400.ttf
      sizes:
        radius: 25

      groups:
        text-like: [text, rest, provider, providertemplate, notifiabletext, label]
      defaults:
        text-like:
          font_path: !font regular
          color: !color text
        grid:
          widget_corner_radius: !size radius

Every key of ``theme`` other than ``groups`` and ``defaults`` is a token
section, and the section name doubles as the YAML tag that reads from it:
``!color panel`` means ``theme.colors.panel``. A tag rather than a string
sentinel like ``$panel`` because widgets.yaml is full of scalars where a
``$`` is real content -- jq expressions, Jinja templates, format strings --
and a tag can't collide with any of them. It also means resolution is an
``isinstance`` check instead of a regex over every string in the document.

Resolution happens after the whole document is parsed, not inside the YAML
constructor: a ``!color`` under ``widgets:`` is constructed before
``theme:`` has been read whenever the theme block is written lower down the
file. So the constructor only records a :class:`Token`, and
:func:`apply_theme` replaces those once everything is loaded.

Nothing in this module knows which parameters a widget takes or what type
they are. The document walk reads one key, ``widget``, to decide which
defaults apply to a node; every other key and value is copied through
untouched, and the widget classes go on validating their own parameters.
"""

from __future__ import annotations

import copy
from typing import Any, Iterator

import yaml

# Keys of the theme block that configure theming itself rather than naming
# values. Every other key is a token section.
RESERVED_SECTIONS = ("groups", "defaults")


class ThemeError(Exception):
    """Raised for an unknown token, a malformed theme block, or a token cycle."""


class Token:
    """A ``!<section> <name>`` reference, standing in for its theme value
    between parse time and :func:`apply_theme`."""

    __slots__ = ("section", "name")

    def __init__(self, section: str, name: str) -> None:
        self.section = section
        self.name = name

    def __repr__(self) -> str:
        return f"!{self.section} {self.name}"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Token):
            return NotImplemented
        return (self.section, self.name) == (other.section, other.name)

    def __hash__(self) -> int:
        return hash((self.section, self.name))


def _token_constructor(loader: Any, tag_suffix: str, node: Any) -> Token:
    if not isinstance(node, yaml.ScalarNode):
        raise ThemeError(
            f"'!{tag_suffix}' must name a single theme entry, "
            f"as in '!{tag_suffix} panel'"
        )
    return Token(tag_suffix, node.value)


def register_constructors() -> None:
    """Teach PyYAML to read any ``!something value`` as a :class:`Token`.

    One multi-constructor rather than a registration per section, because
    the section names live in the file being parsed and aren't known until
    it has been read. PyYAML checks exact-tag constructors before prefix
    ones, so ``!secret`` keeps its own handler.
    """
    yaml.add_multi_constructor("!", _token_constructor)


def theme_sections(document: Any) -> dict[str, Any]:
    """The token sections of a document's theme block, keyed by section name."""
    if not isinstance(document, dict):
        return {}
    theme = document.get("theme")
    if not isinstance(theme, dict):
        return {}
    return {k: v for k, v in theme.items() if k not in RESERVED_SECTIONS}


def section_for_tag(sections: dict[str, Any], section_name: str) -> Any:
    """The section a ``!<section_name>`` tag reads from, or ``None``.

    So a ``!color`` tag can be backed by either ``colors:`` or ``color:``.
    The editor needs the same rule to know which entries a token picker may
    offer, so it lives here rather than inline in :func:`lookup`.
    """
    section = sections.get(section_name)
    if section is None:
        section = sections.get(section_name + "s")
    return section


def lookup(sections: dict[str, Any], section_name: str, entry_name: str) -> Any:
    """The raw theme value a token points at, before any further resolution."""
    section = section_for_tag(sections, section_name)
    if section is None:
        known = ", ".join(sorted(sections)) or "none"
        raise ThemeError(
            f"'!{section_name}' has no matching theme section "
            f"(theme defines: {known})"
        )
    if not isinstance(section, dict):
        raise ThemeError(
            f"theme section '{section_name}' must be a mapping of name to value"
        )
    if entry_name not in section:
        known = ", ".join(sorted(str(k) for k in section)) or "none"
        raise ThemeError(
            f"'!{section_name} {entry_name}' is not defined "
            f"({section_name} defines: {known})"
        )
    return section[entry_name]


def _resolve(
    value: Any,
    sections: dict[str, Any],
    path: str,
    trail: tuple[tuple[str, str], ...] = (),
) -> Any:
    if isinstance(value, Token):
        key = (value.section, value.name)
        if key in trail:
            chain = " -> ".join(f"!{s} {n}" for s, n in trail + (key,))
            raise ThemeError(f"{path}: theme tokens reference each other in a loop: {chain}")
        try:
            target = lookup(sections, value.section, value.name)
        except ThemeError as e:
            raise ThemeError(f"{path}: {e}") from None
        # A theme entry may itself be (or contain) a token, so keep going.
        return _resolve(target, sections, path, trail + (key,))
    if isinstance(value, dict):
        return {
            k: _resolve(v, sections, f"{path}.{k}", trail) for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve(v, sections, f"{path}[{i}]", trail) for i, v in enumerate(value)
        ]
    return value


def defaults_with_source(theme: Any) -> dict[str, dict[str, tuple[Any, str]]]:
    """Like :func:`defaults_by_widget_type`, but each value is paired with the
    name of the ``theme.defaults`` entry it came from -- a group name or a
    widget type.

    Only the editor needs the provenance, to tell you where an inherited
    value is set before you override it; the loader throws it away.
    """
    if not isinstance(theme, dict):
        return {}

    groups = theme.get("groups") or {}
    defaults = theme.get("defaults") or {}
    if not isinstance(groups, dict):
        raise ThemeError(
            "theme.groups must be a mapping of group name to a list of widget types"
        )
    if not isinstance(defaults, dict):
        raise ThemeError(
            "theme.defaults must be a mapping of widget type or group name "
            "to that type's default parameters"
        )

    by_type: dict[str, dict[str, tuple[Any, str]]] = {}
    direct: list[tuple[str, dict[str, Any]]] = []

    def record(widget_type: str, values: dict[str, Any], source: str) -> None:
        entry = by_type.setdefault(widget_type, {})
        for name, value in values.items():
            entry[name] = (value, source)

    for key, values in defaults.items():
        if not isinstance(values, dict):
            raise ThemeError(
                f"theme.defaults.{key} must be a mapping of parameter name to value"
            )
        if key not in groups:
            direct.append((key, values))
            continue
        members = groups[key]
        if not isinstance(members, list):
            raise ThemeError(f"theme.groups.{key} must be a list of widget types")
        for widget_type in members:
            record(widget_type, values, key)

    # Applied last so that naming a widget type outright always beats the
    # defaults it picks up from a group, whichever order the two were written in.
    for widget_type, values in direct:
        record(widget_type, values, widget_type)

    return by_type


def defaults_by_widget_type(theme: Any) -> dict[str, dict[str, Any]]:
    """Flatten ``theme.defaults`` (which may be keyed by group) to one entry
    per widget type.

    Group membership is declared in the file, in ``theme.groups``, so that
    "everything that draws text" can be themed in one place without this
    module knowing anything about widget classes.
    """
    return {
        widget_type: {name: value for name, (value, _source) in entry.items()}
        for widget_type, entry in defaults_with_source(theme).items()
    }


def apply_defaults(document: Any) -> Any:
    """Merge ``theme.defaults`` into every widget node of ``document`` that
    doesn't already set the parameter. Mutates and returns the document.

    Separate from :func:`apply_theme` because the editor and yamltool need to
    know what a node will really be built with, while working on a ruamel
    round-trip document that they must not resolve tokens in.
    """
    if not isinstance(document, dict):
        return document
    by_type = defaults_by_widget_type(document.get("theme"))
    if by_type:
        for key, value in document.items():
            # The theme block itself isn't part of the widget tree.
            if key != "theme":
                _apply_defaults(value, by_type)
    return document


def _apply_defaults(value: Any, by_type: dict[str, dict[str, Any]]) -> None:
    if isinstance(value, dict):
        widget_type = value.get("widget")
        if isinstance(widget_type, str):
            for key, default in by_type.get(widget_type, {}).items():
                if key not in value:
                    # Deep copy: without it every node defaulted from the same
                    # entry would share one mutable list, and a later in-place
                    # edit to any of them would show up in all the others.
                    value[key] = copy.deepcopy(default)
        for child in value.values():
            _apply_defaults(child, by_type)
    elif isinstance(value, list):
        for item in value:
            _apply_defaults(item, by_type)


def find_tokens(value: Any, path: str = "") -> Iterator[tuple[str, Token]]:
    """Yield every ``(path, token)`` still present in a loaded document."""
    if isinstance(value, Token):
        yield path or "(root)", value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from find_tokens(v, f"{path}.{k}" if path else str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from find_tokens(v, f"{path}[{i}]")


def reject_tokens(document: Any, filename: str) -> None:
    """Raise if a theme token turns up in a file that has no theme block.

    Registering the tag handler is global, so ``!color foo`` in conf.yaml or
    providers.yaml now parses instead of failing outright the way an unknown
    tag used to. Catch it here rather than letting it reach a schema check
    that would report something unrecognisable.
    """
    found = list(find_tokens(document))
    if not found:
        return
    where = ", ".join(f"{path} ({token!r})" for path, token in found[:3])
    raise ThemeError(
        f"{filename}: theme tokens are only resolved in the widgets file, "
        f"but this one uses {where}"
    )


def apply_theme(document: Any) -> Any:
    """Merge ``theme.defaults`` into every widget node, then replace every
    token with the value it names. Returns the resolved document."""
    if not isinstance(document, dict):
        return document

    theme = document.get("theme")
    if theme is not None and not isinstance(theme, dict):
        raise ThemeError("theme must be a mapping")

    apply_defaults(document)

    sections = theme_sections(document)
    return {key: _resolve(value, sections, key) for key, value in document.items()}
