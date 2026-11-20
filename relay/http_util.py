from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any


DEFAULT_UA = (
    "Mozilla/5.0 (compatible; ProjectMoonRelay/1.0; +https://github.com/)"
)


def user_agent() -> str:
    return os.environ.get("HTTP_USER_AGENT", DEFAULT_UA)


def fetch(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    allow_redirects: bool = True,
) -> tuple[int, bytes, str]:
    """Return (status, body, final_url). Raises on network failure."""
    req_headers = {"User-Agent": user_agent(), "Accept": "*/*"}
    if headers:
        req_headers.update(headers)

    body = data
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)

    ctx = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
    )
    if not allow_redirects:
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return None

        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            _NoRedirect(),
        )

    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.getcode() or 200, resp.read(), resp.geturl()
    except urllib.error.HTTPError as exc:
        payload = exc.read() if exc.fp else b""
        return exc.code, payload, url


def fetch_json(url: str, **kwargs: Any) -> tuple[int, Any, str]:
    status, body, final = fetch(url, **kwargs)
    if not body:
        return status, None, final
    try:
        return status, json.loads(body.decode("utf-8")), final
    except json.JSONDecodeError:
        return status, None, final


def post_json(url: str, payload: dict[str, Any], **kwargs: Any) -> tuple[int, bytes]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", **(kwargs.pop("headers", {}) or {})}
    status, body, _ = fetch(url, method="POST", data=data, headers=headers, **kwargs)
    return status, body
