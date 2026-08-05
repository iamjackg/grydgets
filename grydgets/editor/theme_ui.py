"""Which theme tokens the editor may offer for a given field.

The loader (:mod:`grydgets.theme`) deliberately never learns what a parameter
*means*: it sees ``!color panel``, finds ``theme.colors.panel``, and hands the
value over without caring that the field is a colour. The editor does know --
schema.json says a field is a colour (``$ref: #/definitions/color``) or a
number -- so the mapping from a form control to the theme section it can draw
on belongs here, on the UI side, and not in the loader.

Only that mapping is written down. Whether a section exists at all is always
read from the document being edited, so a theme with no ``sizes:`` simply
offers no token on numeric fields rather than showing an empty picker. A
field with no matching section that nonetheless holds a token is rendered
read-only by the inspector -- see ``token_capable`` below and the guard in
``update_node``.
"""

from grydgets import theme
from grydgets.editor import yamlio


class TokenOption:
    """One entry of a theme section, as offered in a field's token picker."""

    __slots__ = ("tag", "name", "value")

    def __init__(self, tag, name, value):
        self.tag = tag
        self.name = name
        self.value = value

    @property
    def display(self):
        return f"!{self.tag} {self.name}"

    @property
    def preview(self):
        """The value the token stands for, short enough to sit in an <option>."""
        text = str(self.value)
        return text if len(text) <= 40 else text[:37] + "..."

    @property
    def form_value(self):
        """``"color panel"`` -- the tag and entry name a form posts back.

        Split on the first space: a YAML tag can't contain one, while an
        entry name written as ``!color off white`` can.
        """
        return f"{self.tag} {self.name}"


def tag_for_field(field):
    """The token tag a field can be filled from, or None if none fits.

    Font paths go by name rather than by control because a font path is just
    a string as far as the schema is concerned -- there is nothing else to
    tell ``font_path`` apart from ``url``.
    """
    if field.control == "color":
        return "color"
    if field.name == "font_path" or field.name.endswith("_font_path"):
        return "font"
    if field.control == "number":
        return "size"
    return None


def token_options(doc, field):
    """Every token `field` could be pointed at, in the order the theme lists
    them. Empty when the document's theme has no section for this kind of
    field, which is also what makes the field's picker disappear."""
    tag = tag_for_field(field)
    if tag is None:
        return []
    sections = theme.theme_sections(doc)
    section = theme.section_for_tag(sections, tag)
    if not isinstance(section, dict):
        return []
    return [TokenOption(tag, str(name), value) for name, value in section.items()]


def options_by_field(doc, spec):
    """``{field_name: [TokenOption, ...]}`` for every field of `spec` that has
    somewhere to draw a token from. Fields absent from the mapping get no
    picker, and membership is what ``update_node`` uses to decide whether a
    field's token is editable or read-only."""
    if spec is None:
        return {}
    options = {}
    for field in spec.fields.values():
        found = token_options(doc, field)
        if found:
            options[field.name] = found
    return options


def parse_token_value(form, prefix):
    """The token a token-capable field's picker posted back, or None if the
    user left it on ``-- choose --``."""
    raw = form.get(f"{prefix}_token", "").strip()
    if not raw or " " not in raw:
        return None
    tag, name = raw.split(" ", 1)
    return yamlio.make_token(tag, name)


def wants_token(form, prefix):
    """True when the field's mode radio is set to 'theme'."""
    return form.get(f"{prefix}_kind") == "theme"


def same_token(current, candidate):
    """True when both are theme tokens naming the same entry, so that an
    Apply that didn't touch the field doesn't mark the document dirty."""
    if not (yamlio.is_theme_token(current) and yamlio.is_theme_token(candidate)):
        return False
    return yamlio.token_parts(current) == yamlio.token_parts(candidate)
