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

from grydgets import rest_fetch
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


def _to_plain(value: Any, secrets: dict[str, Any]) -> Any:
    """Recursively convert ruamel containers/scalars to plain Python,
    substituting ``!secret name`` with its value from secrets.yaml (or None
    if the key is absent)."""
    if yamlio.is_secret(value):
        return secrets.get(value.value)
    if isinstance(value, dict):
        return {k: _to_plain(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v, secrets) for v in value]
    return value


def resolve_node(node, secrets_path: str) -> dict[str, Any]:
    """Node -> plain-value parameter dict with secrets resolved."""
    secrets = _load_secret_values(secrets_path)
    return {k: _to_plain(v, secrets) for k, v in node.items()}


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


def test_rest(node, secrets_path: str) -> tuple[dict[str, Any], rest_fetch.RestTextResult]:
    params = resolve_node(node, secrets_path)
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


def test_image(node, secrets_path: str) -> tuple[dict[str, Any], rest_fetch.RestImageResult]:
    params = resolve_node(node, secrets_path)
    result = rest_fetch.fetch_image(
        url=params.get("url") or "",
        json_path=params.get("json_path"),
        jq_expression=params.get("jq_expression"),
        auth=params.get("auth"),
        timeout=REQUEST_TIMEOUT,
    )
    return request_summary(params), result
