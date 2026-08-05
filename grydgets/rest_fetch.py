"""Shared HTTP fetch + JSON extraction for the REST widgets.

The fetch/extract/format pipeline used to live inline inside each widget's
``update()``. It's pulled out here so the editor's "test request" panel can
run *exactly* the same code path a widget runs -- a preview that diverged
from the real behaviour would be worse than no preview at all.

The functions return a staged result object (status, raw body, extracted
value, final value) rather than just the final string, so the editor can show
each step of the pipeline. The widgets only look at the final field.

Fallback semantics (``"Error {code}"`` on non-200, ``"Unavailable"`` on a
connection error, ``"--"`` on a failed extraction) are preserved from the
original widget code so the refactor is behaviour-preserving. ``timeout``
defaults to ``None`` to match the widgets' original (timeout-less) requests;
the editor passes an explicit timeout so a hung endpoint can't wedge it.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import requests

from grydgets.json_utils import extract_data


def build_auth_headers(auth: dict[str, Any] | None) -> dict[str, str]:
    """Turn a widget ``auth`` mapping into request headers.

    Mirrors the (previously duplicated) header-building in RESTWidget and
    RESTImageWidget: ``{"bearer": tok}`` -> Bearer, ``{"basic": {...}}`` ->
    base64 Basic. Values are expected to already be resolved (no ``!secret``).
    """
    headers: dict[str, str] = {}
    if not auth:
        return headers
    if "bearer" in auth:
        headers["Authorization"] = "Bearer {}".format(auth["bearer"])
    elif "basic" in auth:
        username = auth["basic"].get("username", "")
        password = auth["basic"].get("password", "")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    return headers


@dataclass
class RestTextResult:
    """Staged result of the text (``rest`` widget) pipeline."""

    value: str = ""  # final formatted text -- what the widget renders
    connection_error: str | None = None  # transport failure (-> "Unavailable")
    status_code: int | None = None
    elapsed_ms: float | None = None
    raw_text: str | None = None
    json: Any = None  # parsed body when extraction ran (cached for re-extract)
    is_json: bool = False
    extracted: Any = None
    extraction_error: str | None = None


def apply_extraction(
    data: Any,
    json_path: str | None,
    jq_expression: str | None,
    format_string: str = "{}",
) -> tuple[str, Any, str | None]:
    """Run json_path/jq extraction + format_string against an already-parsed
    body. Returns ``(formatted_value, extracted, extraction_error)``.

    Broken out so the editor can re-run just this step against a cached
    response when the user tweaks the path/expression, with no new request.
    Matches the widget: a failed extraction yields ``"--"``.
    """
    if json_path is None and jq_expression is None:
        # No extraction configured: the widget uses the raw response text.
        text = data if isinstance(data, str) else str(data)
        return format_string.format(text), None, None
    try:
        extracted = extract_data(data, json_path=json_path, jq_expression=jq_expression)
    except Exception as exc:
        return format_string.format("--"), None, str(exc)
    return format_string.format(extracted), extracted, None


def fetch_text(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    auth: dict[str, Any] | None = None,
    json_path: str | None = None,
    jq_expression: str | None = None,
    format_string: str = "{}",
    timeout: float | None = None,
) -> RestTextResult:
    """Fetch ``url`` and run the ``rest`` widget's text pipeline.

    Never raises for a connection error (records it and returns
    ``"Unavailable"``, as the widget does). Other request exceptions
    propagate to the caller.
    """
    result = RestTextResult()
    format_string = format_string or "{}"
    headers = build_auth_headers(auth)
    request_kwargs: dict[str, Any] = {"headers": headers}
    if method in ("POST", "PUT", "PATCH") and payload:
        request_kwargs["json"] = payload

    try:
        start = time.monotonic()
        response = requests.request(method=method, url=url, timeout=timeout, **request_kwargs)
    except requests.ConnectionError as exc:
        result.connection_error = str(exc)
        result.value = format_string.format("Unavailable")
        return result

    result.elapsed_ms = (time.monotonic() - start) * 1000
    result.status_code = response.status_code
    result.raw_text = response.text

    if response.status_code != 200:
        result.value = format_string.format("Error {}".format(response.status_code))
        return result

    if json_path is not None or jq_expression is not None:
        result.is_json = True
        try:
            result.json = response.json()
        except ValueError as exc:
            result.extraction_error = str(exc)
            result.value = format_string.format("--")
            return result
        value, extracted, err = apply_extraction(
            result.json, json_path, jq_expression, format_string
        )
        result.value = value
        result.extracted = extracted
        result.extraction_error = err
    else:
        result.value = format_string.format(response.text)

    return result


@dataclass
class RestImageResult:
    """Staged result of the image (``restimage`` widget) pipeline."""

    image_bytes: bytes | None = None  # final image bytes -- what the widget loads
    error: str | None = None
    status_code: int | None = None
    elapsed_ms: float | None = None
    extracted_url: str | None = None  # image URL pulled from a JSON response
    extraction_error: str | None = None
    content_type: str | None = None


def _read_file_url(file_url: str) -> bytes:
    with open(file_url[len("file://"):], "rb") as f:
        return f.read()


def fetch_image(
    url: str,
    json_path: str | None = None,
    jq_expression: str | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> RestImageResult:
    """Fetch an image the way the ``restimage`` widget does.

    Supports ``file://`` sources, and the two-step "fetch JSON, extract an
    image URL, fetch that" flow. Transport/file errors are captured on the
    result rather than raised.
    """
    result = RestImageResult()

    try:
        if url.startswith("file://"):
            result.image_bytes = _read_file_url(url)
            return result

        headers = build_auth_headers(auth)
        start = time.monotonic()
        response = requests.get(url, headers=headers, timeout=timeout)
        result.elapsed_ms = (time.monotonic() - start) * 1000
        result.status_code = response.status_code

        if json_path is not None or jq_expression is not None:
            try:
                image_url = extract_data(
                    response.json(), json_path=json_path, jq_expression=jq_expression
                )
            except Exception as exc:
                result.extraction_error = str(exc)
                return result
            result.extracted_url = image_url
            if isinstance(image_url, str) and image_url.startswith("file://"):
                result.image_bytes = _read_file_url(image_url)
            else:
                image_response = requests.get(image_url, timeout=timeout)
                result.content_type = image_response.headers.get("Content-Type")
                result.image_bytes = image_response.content
        else:
            result.content_type = response.headers.get("Content-Type")
            result.image_bytes = response.content
    except (requests.RequestException, OSError) as exc:
        result.error = str(exc)

    return result
