from __future__ import annotations

import time
from typing import Any

from .http_util import post_json


def send_webhook(
    webhook_url: str,
    *,
    content: str | None = None,
    embeds: list[dict[str, Any]] | None = None,
    username: str | None = None,
    avatar_url: str | None = None,
    retries: int = 3,
) -> None:
    payload: dict[str, Any] = {}
    if content:
        payload["content"] = content[:2000]
    if embeds:
        payload["embeds"] = embeds[:10]
    if username:
        payload["username"] = username[:80]
    if avatar_url:
        payload["avatar_url"] = avatar_url

    if not payload.get("content") and not payload.get("embeds"):
        raise ValueError("Discord webhook needs content or embeds")

    last_error: Exception | None = None
    for attempt in range(retries):
        status, body = post_json(webhook_url, payload, timeout=30.0)
        if status in (200, 204):
            return
        if status == 429:
            wait = 2.0
            try:
                import json

                wait = float(json.loads(body.decode("utf-8")).get("retry_after", 2))
            except Exception:
                pass
            time.sleep(min(max(wait, 1.0), 30.0))
            continue
        last_error = RuntimeError(f"Discord webhook HTTP {status}: {body[:300]!r}")
        time.sleep(1.5 * (attempt + 1))
    raise last_error or RuntimeError("Discord webhook failed")


def tweet_embed(post: dict[str, Any], color: int) -> dict[str, Any]:
    author = post.get("author") or {}
    name = author.get("name") or author.get("screen_name") or "X"
    handle = author.get("screen_name") or ""
    avatar = author.get("avatar_url")
    text = (post.get("text") or "").strip() or "(media)"
    url = post.get("url") or ""

    prefix = ""
    if post.get("reposted_by"):
        prefix = "🔁 Repost\n"
    elif post.get("replying_to"):
        prefix = "💬 Reply\n"

    embed: dict[str, Any] = {
        "description": f"{prefix}{text}"[:4096],
        "url": url,
        "color": color,
        "author": {
            "name": f"{name} (@{handle})" if handle else name,
            "url": author.get("url") or (f"https://x.com/{handle}" if handle else url),
        },
    }
    if avatar:
        embed["author"]["icon_url"] = avatar

    media = post.get("media") or {}
    image_url = None
    photos = media.get("photos") or []
    videos = media.get("videos") or []
    mosaic = (media.get("mosaic") or {}).get("formats") or {}
    if mosaic.get("jpeg"):
        image_url = mosaic["jpeg"]
    elif photos:
        image_url = photos[0].get("url")
    elif videos:
        image_url = videos[0].get("thumbnail_url")
    elif (media.get("all") or []):
        first = media["all"][0]
        image_url = first.get("thumbnail_url") or first.get("url")
    if image_url:
        embed["image"] = {"url": image_url}

    if post.get("created_at"):
        # Discord expects ISO8601; FxTwitter uses "Fri Nov 20 ..." — leave as footer.
        embed["footer"] = {"text": f"X · {post['created_at']}"}

    return embed


def youtube_live_embed(live: dict[str, Any], color: int) -> dict[str, Any]:
    title = live.get("title") or "Live stream"
    url = live.get("url") or ""
    channel = live.get("channel_title") or live.get("handle") or "YouTube"
    thumb = live.get("thumbnail_url")

    embed: dict[str, Any] = {
        "title": f"🔴 LIVE: {title}"[:256],
        "url": url,
        "description": f"**{channel}** сейчас в эфире",
        "color": color,
    }
    if thumb:
        embed["image"] = {"url": thumb}
    return embed
