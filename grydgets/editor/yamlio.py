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


def is_secret(value):
    """True if value is a preserved tagged scalar with the !secret tag."""
    if not isinstance(value, TaggedScalar):
        return False
    tag = value.tag
    tag_str = tag.value if hasattr(tag, "value") else tag
    return tag_str == "!secret"


def secret_display(value):
    """A read-only display string for a tagged scalar, e.g. '!secret hass_token'."""
    tag = value.tag
    tag_str = tag.value if hasattr(tag, "value") else tag
    return f"!{tag_str.lstrip('!')} {value.value}"


def make_secret(key):
    """Build a !secret tagged scalar referencing `key` in secrets.yaml."""
    return TaggedScalar(value=key, tag="!secret")


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
