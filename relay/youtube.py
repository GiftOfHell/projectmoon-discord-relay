from __future__ import annotations

import json
import re
from typing import Any

from .http_util import fetch


VIDEO_ID_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/live/)([\w-]{11})")
IS_LIVE_RE = re.compile(r'"isLiveNow"\s*:\s*true')
VIDEO_DETAILS_RE = re.compile(
    r'"videoDetails"\s*:\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})'
)
SIMPLE_TITLE_RE = re.compile(r'"title"\s*:\s*"((?:\\.|[^"\\])*)"')
SIMPLE_VIDEO_ID_RE = re.compile(r'"videoId"\s*:\s*"([\w-]{11})"')
CHANNEL_TITLE_RE = re.compile(r'"ownerChannelName"\s*:\s*"((?:\\.|[^"\\])*)"')


def check_live(handle: str, channel_id: str | None = None) -> dict[str, Any] | None:
    """
    Return live info if the channel is currently streaming, else None.
    Uses the public /live page — no YouTube API key required.
    """
    candidates = [
        f"https://www.youtube.com/@{handle.lstrip('@')}/live",
    ]
    if channel_id:
        candidates.append(f"https://www.youtube.com/channel/{channel_id}/live")

    last_error: Exception | None = None
    for url in candidates:
        try:
            status, body, final_url = fetch(url, timeout=30.0)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        if status != 200 or not body:
            continue
        html = body.decode("utf-8", errors="replace")
        live = _parse_live_html(html, final_url=final_url, handle=handle)
        if live:
            return live
        # Offline /live page usually has no isLiveNow — treat as not live.
        return None

    if last_error:
        raise RuntimeError(f"YouTube live check failed for @{handle}: {last_error}") from last_error
    return None


def _parse_live_html(html: str, *, final_url: str, handle: str) -> dict[str, Any] | None:
    if not IS_LIVE_RE.search(html):
        # Sometimes final URL is already /watch?v= while live; double-check player JSON.
        if "/watch" not in final_url and "/live/" not in final_url:
            return None
        if '"isLive":true' not in html and '"isLiveContent":true' not in html:
            return None

    video_id = None
    title = None
    channel_title = None

    m = VIDEO_DETAILS_RE.search(html)
    if m:
        try:
            # videoDetails blob is not always strict JSON due to truncation; fall back to regex.
            blob = m.group(1)
            vid = re.search(r'"videoId"\s*:\s*"([\w-]{11})"', blob)
            tit = re.search(r'"title"\s*:\s*"((?:\\.|[^"\\])*)"', blob)
            ch = re.search(r'"author"\s*:\s*"((?:\\.|[^"\\])*)"', blob)
            if vid:
                video_id = vid.group(1)
            if tit:
                title = _unescape_json_str(tit.group(1))
            if ch:
                channel_title = _unescape_json_str(ch.group(1))
        except Exception:
            pass

    if not video_id:
        m = SIMPLE_VIDEO_ID_RE.search(html)
        if m:
            video_id = m.group(1)
    if not video_id:
        m = VIDEO_ID_RE.search(final_url) or VIDEO_ID_RE.search(html)
        if m:
            video_id = m.group(1)
    if not video_id:
        return None

    if not title:
        m = SIMPLE_TITLE_RE.search(html)
        if m:
            title = _unescape_json_str(m.group(1))
    if not channel_title:
        m = CHANNEL_TITLE_RE.search(html)
        if m:
            channel_title = _unescape_json_str(m.group(1))

    # Require a live marker when we only found a video id on a generic page.
    if not IS_LIVE_RE.search(html) and '"isLive":true' not in html:
        # /live offline pages can still mention old videoIds in related content.
        if "/watch" not in final_url:
            return None

    return {
        "video_id": video_id,
        "title": title or "Live stream",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "channel_title": channel_title or handle,
        "handle": handle,
    }


def _unescape_json_str(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return value.encode("utf-8").decode("unicode_escape", errors="replace")
