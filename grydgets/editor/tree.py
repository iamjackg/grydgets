"""Node addressing over the in-memory widgets.yaml document.

Every node is identified by its path from the root, e.g.
``widgets/0/children/1/children/3``: alternating (key, index) pairs where the
first pair is always ``widgets`` (the document's top-level array) and every
subsequent pair is ``children`` (a widget's child array).

Paths are resolved fresh against the in-memory doc on every request and are
never expected to survive across requests -- each mutation does
read -> mutate -> re-render the affected subtree atomically, so the HTML
fragment returned always carries correct, current paths.
"""

from ruamel.yaml.comments import CommentedSeq


class NodeNotFound(Exception):
    pass


def parse_path(path):
    parts = path.split("/")
    if len(parts) % 2 != 0:
        raise ValueError(f"malformed node path: {path!r}")
    segments = []
    for i in range(0, len(parts), 2):
        key = parts[i]
        try:
            idx = int(parts[i + 1])
        except ValueError:
            raise ValueError(f"malformed node path: {path!r}")
        segments.append((key, idx))
    return segments


def child_path(parent_path, index):
    if parent_path is None:
        return f"widgets/{index}"
    return f"{parent_path}/children/{index}"


def get_node(doc, path):
    """Resolve a path to the widget dict it addresses."""
    node = doc
    try:
        for key, idx in parse_path(path):
            node = node[key][idx]
    except (KeyError, IndexError, TypeError) as exc:
        raise NodeNotFound(path) from exc
    return node


def _resolve_container(doc, path):
    """Return (container, key, index) where container[key][index] is the node at path."""
    segments = parse_path(path)
    container = doc
    try:
        for key, idx in segments[:-1]:
            container = container[key][idx]
        last_key, last_idx = segments[-1]
        # touch it to raise if missing
        container[last_key][last_idx]
    except (KeyError, IndexError, TypeError) as exc:
        raise NodeNotFound(path) from exc
    return container, last_key, last_idx


def get_parent_path(path):
    segments = parse_path(path)
    if len(segments) == 1:
        return None
    parent_segments = segments[:-1]
    return "/".join(f"{key}/{idx}" for key, idx in parent_segments)


def iter_tree(doc):
    """Yield (path, node) for every widget node in the document, depth-first."""
    for i, node in enumerate(doc.get("widgets") or []):
        yield from _walk(node, f"widgets/{i}")


def _walk(node, path):
    yield path, node
    for i, child in enumerate(node.get("children") or []):
        yield from _walk(child, f"{path}/children/{i}")


def get_children(node):
    return list(node.get("children") or [])


def add_child(doc, parent_path, new_node, index=None):
    """Add new_node into parent_path's children (or top-level widgets if parent_path is None)."""
    if parent_path is None:
        if "widgets" not in doc or doc["widgets"] is None:
            doc["widgets"] = CommentedSeq()
        lst = doc["widgets"]
    else:
        parent_node = get_node(doc, parent_path)
        if "children" not in parent_node or parent_node["children"] is None:
            parent_node["children"] = CommentedSeq()
        lst = parent_node["children"]

    if index is None or index >= len(lst):
        lst.append(new_node)
    else:
        lst.insert(index, new_node)


def delete_node(doc, path):
    container, key, idx = _resolve_container(doc, path)
    del container[key][idx]


def move_node(doc, path, new_index):
    """Reorder a node within its parent's list. Returns the node's new path."""
    container, key, idx = _resolve_container(doc, path)
    lst = container[key]
    node = lst.pop(idx)
    new_index = max(0, min(new_index, len(lst)))
    lst.insert(new_index, node)
    parent_path = get_parent_path(path)
    return child_path(parent_path, new_index)


def find_siblings(doc, path):
    """Return the list of sibling nodes (including this one) that share path's parent."""
    container, key, idx = _resolve_container(doc, path)
    return list(container[key])
