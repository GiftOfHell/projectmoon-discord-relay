from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

from .http_util import fetch, fetch_json


STATUS_ID_RE = re.compile(r"/status/(\d+)")


def fetch_posts(
    handle: str,
    *,
    api_hosts: list[str],
    rss_hosts: list[str],
    count: int = 20,
    attempts: int = 3,
    include_replies: bool = False,
) -> list[dict[str, Any]]:
    """Fetch recent posts. Retries on transient FxTwitter/RSS failures."""
    last_error = "unknown"
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            return _fetch_posts_once(
                handle,
                api_hosts=api_hosts,
                rss_hosts=rss_hosts,
                count=count,
                include_replies=include_replies,
            )
        except RuntimeError as exc:
            last_error = str(exc)
            if attempt >= attempts:
                break
            time.sleep(1.5 * attempt)
    raise RuntimeError(last_error)


def _fetch_posts_once(
    handle: str,
    *,
    api_hosts: list[str],
    rss_hosts: list[str],
    count: int,
    include_replies: bool,
) -> list[dict[str, Any]]:
    errors: list[str] = []
    reply_q = "&with_replies=1" if include_replies else ""

    for host in api_hosts:
        url = (
            f"{host.rstrip('/')}/2/profile/{quote(handle)}/statuses"
            f"?count={count}{reply_q}"
        )
        try:
            status, data, _ = fetch_json(url, timeout=30.0)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"api {host}: {exc}")
            continue
        if status == 200 and isinstance(data, dict) and isinstance(data.get("results"), list):
            return [
                p
                for p in data["results"]
                if isinstance(p, dict) and p.get("type") == "status"
            ]
        errors.append(f"api {host}: HTTP {status}")

    for host in rss_hosts:
        url = f"{host.rstrip('/')}/{quote(handle)}/feed.xml?count={count}"
        try:
            status, body, _ = fetch(url, timeout=30.0)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"rss {host}: {exc}")
            continue
        if status == 200 and body:
            posts = _parse_rss(body, fallback_handle=handle)
            if posts:
                return posts
        errors.append(f"rss {host}: HTTP {status}")

    raise RuntimeError(
        f"Failed to fetch @{handle}. Tried API+RSS. Details: " + "; ".join(errors[-6:])
    )


def filter_posts(
    posts: list[dict[str, Any]],
    *,
    handle: str,
    exclude_replies: bool,
    exclude_reposts: bool,
    only_self_replies: bool = False,
    require_text_contains: list[str] | None = None,
) -> list[dict[str, Any]]:
    handle_l = handle.lstrip("@").lower()
    needles = [n.lower() for n in (require_text_contains or []) if n]
    out: list[dict[str, Any]] = []
    for post in posts:
        if exclude_reposts and post.get("reposted_by"):
            continue

        replying_to = post.get("replying_to")
        if replying_to:
            if exclude_replies:
                continue
            if only_self_replies:
                # Accept only replies in his own thread (translation follow-ups).
                target = ""
                if isinstance(replying_to, dict):
                    target = (
                        replying_to.get("screen_name")
                        or (replying_to.get("author") or {}).get("screen_name")
                        or ""
                    )
                elif isinstance(replying_to, str):
                    target = replying_to
                if target.lstrip("@").lower() != handle_l:
                    continue

        # Keep original posts + (optional) reposts; ignore noise without id.
        if not post.get("id"):
            continue

        if needles:
            blob = _post_search_blob(post)
            if not any(n in blob for n in needles):
                continue

        out.append(post)
    return out


def _post_search_blob(post: dict[str, Any]) -> str:
    parts = [
        str(post.get("text") or ""),
        str(post.get("url") or ""),
    ]
    card = post.get("card") or {}
    if isinstance(card, dict):
        parts.extend(
            [
                str(card.get("url") or ""),
                str(card.get("title") or ""),
                str(card.get("description") or ""),
            ]
        )
    raw = post.get("raw_text") or {}
    if isinstance(raw, dict):
        parts.append(str(raw.get("text") or ""))
        for facet in raw.get("facets") or []:
            if isinstance(facet, dict):
                parts.append(str(facet.get("replacement") or ""))
                parts.append(str(facet.get("original") or ""))
    return "\n".join(parts).lower()


def _parse_rss(body: bytes, *, fallback_handle: str) -> list[dict[str, Any]]:
    root = ET.fromstring(body)
    channel = root.find("channel")
    if channel is None:
        return []

    posts: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        title = (item.findtext("title") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()

        match = STATUS_ID_RE.search(link) or STATUS_ID_RE.search(guid)
        if not match:
            continue
        post_id = match.group(1)

        # Rough HTML strip for description.
        text = re.sub(r"<[^>]+>", "", description).strip() or title
        image_url = None
        enclosure = item.find("enclosure")
        if enclosure is not None and (enclosure.get("type") or "").startswith("image"):
            image_url = enclosure.get("url")

        media: dict[str, Any] = {}
        if image_url:
            media = {"photos": [{"type": "photo", "url": image_url}], "all": [{"type": "photo", "url": image_url}]}

        posts.append(
            {
                "type": "status",
                "id": post_id,
                "url": link or f"https://x.com/{fallback_handle}/status/{post_id}",
                "text": text,
                "created_at": pub,
                "author": {
                    "screen_name": fallback_handle,
                    "name": fallback_handle,
                    "url": f"https://x.com/{fallback_handle}",
                },
                "media": media,
                "reposted_by": None,
                "replying_to": None,
            }
        )
    return posts
