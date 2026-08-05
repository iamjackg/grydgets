"""ruamel.yaml round-trip load/save for widgets.yaml.

Round-trip mode preserves comments, key order, tag style (``!secret``), and
block-scalar style. Unknown tags such as ``!secret`` are loaded as
``ruamel.yaml.comments.TaggedScalar`` automatically -- no custom constructor
needed, and dumping a document that still contains them reproduces the tag
byte-for-byte.

Load the file into an in-memory document once at startup. All edits mutate
that document. "Save" is the only thing that writes to disk -- we never
round-trip through our own serialization mid-session.
"""

import datetime
import io
import shutil
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, TaggedScalar

_yaml = YAML(typ="rt")
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def load_doc(path):
    """Load a widgets.yaml file into a ruamel round-trip document."""
    with open(path, "r") as f:
        return _yaml.load(f) or CommentedMap()


def dump_doc(doc, path):
    """Write a ruamel document to disk.

    Serialize to a string first so a representer error (an un-dumpable value
    somewhere in the doc) is raised *before* the destination file is opened
    for writing -- otherwise the ``open(path, "w")`` truncation would leave a
    half-written/empty widgets.yaml behind.
    """
    content = dump_doc_to_string(doc)
    with open(path, "w") as f:
        f.write(content)


def dump_doc_to_string(doc):
    buf = io.StringIO()
    _yaml.dump(doc, buf)
    return buf.getvalue()


def backup_path(path):
    """Return the timestamped backup path for a widgets.yaml file.

    Matches the existing repo convention: widgets.yaml-YYYYMMDDHHMM.backup
    """
    path = Path(path)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    return path.with_name(f"{path.name}-{timestamp}.backup")


def save_doc(doc, path):
    """Back up the current on-disk file (if present), then write doc to path.

    Returns the backup path that was actually written, or None if there was
    no existing file to back up.
    """
    path = Path(path)
    backup = None
    if path.exists():
        backup = backup_path(path)
        shutil.copy2(path, backup)
    dump_doc(doc, path)
    return backup


def tag_of(value):
    """The tag string of a preserved tagged scalar, or None if it isn't one."""
    if not isinstance(value, TaggedScalar):
        return None
    tag = value.tag
    return tag.value if hasattr(tag, "value") else tag


def is_secret(value):
    """True if value is a preserved tagged scalar with the !secret tag."""
    return tag_of(value) == "!secret"


def is_theme_token(value):
    """True if value is a theme token such as ``!color panel``.

    Every tag other than !secret is a theme token: the section names in the
    theme block are what the tags are named after, so the set isn't fixed and
    can't be enumerated here. Tokens are ordinary editable values, unlike
    secrets, so they must not be routed through is_secret/contains_secret.
    """
    tag = tag_of(value)
    return tag is not None and tag != "!secret"


def token_parts(value):
    """``(section, name)`` for a theme-token scalar: ``!color panel`` gives
    ``("color", "panel")``."""
    return tag_of(value).lstrip("!"), value.value


def secret_display(value):
    """A read-only display string for a tagged scalar, e.g. '!secret hass_token'."""
    tag = value.tag
    tag_str = tag.value if hasattr(tag, "value") else tag
    return f"!{tag_str.lstrip('!')} {value.value}"


def token_display(value):
    """A read-only display string for a theme token, e.g. '!color panel'."""
    return secret_display(value)


def make_secret(key):
    """Build a !secret tagged scalar referencing `key` in secrets.yaml."""
    return TaggedScalar(value=key, tag="!secret")


def make_token(section, name):
    """Build a theme-token scalar: make_token('color', 'panel') is '!color panel'.

    The scalar is what round-trips back to the file, so this is the only way
    the editor may write a token -- assigning the string '!color panel' would
    dump as a quoted string and stop resolving.
    """
    return TaggedScalar(value=name, tag="!" + str(section).lstrip("!"))


def contains_theme_token(value):
    """True if value is, or holds anywhere inside it, a theme token.

    A token nested in a mapping (a bar chart's `bar_colors`, a grid's
    per-cell overrides) is edited through the raw-YAML box, which has to
    parse its contents back with the round-trip loader for the tag to
    survive -- see parse_value.
    """
    if is_theme_token(value):
        return True
    if isinstance(value, dict):
        return any(contains_theme_token(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_theme_token(v) for v in value)
    return False


def parse_value(text):
    """Parse the contents of a raw-YAML box back into a value.

    ruamel's round-trip loader rather than pyyaml's safe_load: safe_load has
    no constructor for `!color panel` or `!secret hass_token` and refuses the
    whole document, so a raw field holding a token or a secret anywhere
    inside it could never be applied. Round-trip loading keeps both as
    tagged scalars, and quote/block style with them.
    """
    return _yaml.load(text)


def contains_secret(value):
    """True if value is, or contains anywhere inside it, a tagged scalar.

    Fields like `auth: {bearer: !secret hass_token}` aren't themselves a
    TaggedScalar -- they're a dict that happens to hold one. Editing that
    dict as a generic raw-YAML textarea would round-trip the secret through
    plain pyyaml and destroy the tag, so any field whose value contains a
    secret anywhere in its subtree must be treated as read-only, same as a
    bare secret scalar.
    """
    if is_secret(value):
        return True
    if isinstance(value, dict):
        return any(contains_secret(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_secret(v) for v in value)
    return False


def dump_value_to_string(value):
    """Dump a single (sub-)value with tag/style preserved, for read-only display."""
    buf = io.StringIO()
    _yaml.dump(value, buf)
    return buf.getvalue().strip()
