"""Backend for the inspector's "test request" panel.

Resolves a ``rest``/``restimage`` node from the in-memory ruamel document to
plain Python values -- including looking up ``!secret`` references in
secrets.yaml -- and runs the shared ``grydgets.rest_fetch`` pipeline so the
panel shows exactly what the widget would receive.

This is the one place in the editor that reads *secret values* (everywhere
else deals only in secret names). It has to, in order to make the same
authenticated request the widget makes. Secret values never reach the
rendered page: request headers are shown redacted, and only the response and
extracted value are displayed.
"""

from __future__ import annotations

from typing import Any

import yaml

from grydgets import rest_fetch, theme
from grydgets.editor import yamlio

# A hung endpoint must not wedge the single-threaded editor.
REQUEST_TIMEOUT = 10
RAW_BODY_LIMIT = 8000  # chars of response body kept for display / re-extraction


def _load_secret_values(secrets_path: str) -> dict[str, Any]:
    try:
        with open(secrets_path) as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _to_plain(
    value: Any,
    secrets: dict[str, Any],
    sections: dict[str, Any],
    trail: tuple[tuple[str, str], ...] = (),
) -> Any:
    """Recursively convert ruamel containers/scalars to plain Python,
    substituting ``!secret name`` with its value from secrets.yaml (or None
    if the key is absent) and a theme token with the value it names, so a
    URL or an auth block written as a token tests the way it renders.

    An unresolvable token, or one that loops, becomes None: both are already
    named in the warnings panel, and the test panel's job is to show what the
    request does, not to re-report the theme.
    """
    if yamlio.is_secret(value):
        return secrets.get(value.value)
    if yamlio.is_theme_token(value):
        section, name = yamlio.token_parts(value)
        if (section, name) in trail:
            return None
        try:
            target = theme.lookup(sections, section, name)
        except theme.ThemeError:
            return None
        return _to_plain(target, secrets, sections, trail + ((section, name),))
    if isinstance(value, dict):
        return {k: _to_plain(v, secrets, sections, trail) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v, secrets, sections, trail) for v in value]
    return value


def resolve_node(
    node,
    secrets_path: str,
    sections: dict[str, Any] | None = None,
    defaults: dict[str, tuple[Any, str]] | None = None,
) -> dict[str, Any]:
    """Node -> plain-value parameter dict with secrets and theme tokens
    resolved.

    ``defaults`` is ``theme.defaults_with_source()`` for this widget type;
    parameters the node doesn't set are filled in from it, so a node whose
    ``url`` or ``auth`` comes from the theme tests with the same values the
    widget is built with. Nothing is written back to the node.
    """
    secrets = _load_secret_values(secrets_path)
    sections = sections or {}
    params = {k: _to_plain(v, secrets, sections) for k, v in node.items()}
    for name, (value, _source) in (defaults or {}).items():
        if name not in params:
            params[name] = _to_plain(value, secrets, sections)
    return params


def _redacted_headers(auth: dict[str, Any] | None) -> dict[str, str]:
    """Header preview that shows an Authorization header *is* being sent
    without revealing the credential."""
    if not auth:
        return {}
    if "bearer" in auth:
        return {"Authorization": "Bearer ••••••"}
    if "basic" in auth:
        return {"Authorization": "Basic ••••••"}
    return {}


def request_summary(params: dict[str, Any]) -> dict[str, Any]:
    method = params.get("method") or "GET"
    return {
        "method": method,
        "url": params.get("url") or "",
        "headers": _redacted_headers(params.get("auth")),
        "payload": params.get("payload") if method in ("POST", "PUT", "PATCH") else None,
        "is_mutation": method in ("POST", "PUT", "PATCH"),
    }


def test_rest(
    node,
    secrets_path: str,
    sections: dict[str, Any] | None = None,
    defaults: dict[str, tuple[Any, str]] | None = None,
) -> tuple[dict[str, Any], rest_fetch.RestTextResult]:
    params = resolve_node(node, secrets_path, sections, defaults)
    result = rest_fetch.fetch_text(
        url=params.get("url") or "",
        method=params.get("method") or "GET",
        payload=params.get("payload"),
        auth=params.get("auth"),
        json_path=params.get("json_path"),
        jq_expression=params.get("jq_expression"),
        format_string=params.get("format_string") or "{}",
        timeout=REQUEST_TIMEOUT,
    )
    if result.raw_text is not None and len(result.raw_text) > RAW_BODY_LIMIT:
        result.raw_text = result.raw_text[:RAW_BODY_LIMIT] + "\n... (truncated)"
    return request_summary(params), result


def test_image(
    node,
    secrets_path: str,
    sections: dict[str, Any] | None = None,
    defaults: dict[str, tuple[Any, str]] | None = None,
) -> tuple[dict[str, Any], rest_fetch.RestImageResult]:
    params = resolve_node(node, secrets_path, sections, defaults)
    result = rest_fetch.fetch_image(
        url=params.get("url") or "",
        json_path=params.get("json_path"),
        jq_expression=params.get("jq_expression"),
        auth=params.get("auth"),
        timeout=REQUEST_TIMEOUT,
    )
    return request_summary(params), result
