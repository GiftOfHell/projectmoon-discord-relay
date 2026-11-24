from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from .discord_webhook import send_webhook, tweet_embed, youtube_live_embed
from .state import StateStore
from .twitter import fetch_posts, filter_posts
from .youtube import check_live


ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def webhook_for(source: dict[str, Any]) -> str:
    env_name = source["webhook_env"]
    url = os.environ.get(env_name, "").strip()
    if not url:
        raise RuntimeError(f"Missing webhook env var: {env_name}")
    return url


def process_x(source: dict[str, Any], cfg: dict[str, Any], state: StateStore, dry_run: bool) -> int:
    handle = source["handle"]
    source_id = source["id"]
    epoch = int(source.get("state_epoch") or 1)
    exclude_replies = bool(source.get("exclude_replies", True))
    only_self_replies = bool(source.get("only_self_replies", False))
    # Need with_replies=1 when we keep any replies (all or self-only).
    include_replies = (not exclude_replies) or only_self_replies
    posts = fetch_posts(
        handle,
        api_hosts=cfg.get("fxtwitter_hosts") or ["https://api.fxtwitter.com"],
        rss_hosts=cfg.get("rss_hosts") or ["https://fxtwitter.com"],
        count=int(cfg.get("fetch_count") or 20),
        attempts=int(cfg.get("fetch_attempts") or 3),
        include_replies=include_replies,
    )
    posts = filter_posts(
        posts,
        handle=handle,
        exclude_replies=exclude_replies and not only_self_replies,
        exclude_reposts=bool(source.get("exclude_reposts", False)),
        only_self_replies=only_self_replies,
        require_text_contains=list(source.get("require_text_contains") or []),
    )

    # Newest first from API; process oldest→newest for Discord order.
    posts = list(reversed(posts))
    known = state.seen_ids(source_id)
    new_posts = [p for p in posts if p["id"] not in known]

    if not state.is_initialized(source_id, epoch=epoch):
        # First run / config epoch bump: remember current timeline, do not spam.
        state.remember_ids(source_id, [p["id"] for p in posts])
        state.mark_initialized(source_id, epoch=epoch)
        state.save()
        print(f"[{source_id}] initialized epoch={epoch} with {len(posts)} posts (no send)")
        return 0

    if not new_posts:
        print(f"[{source_id}] no new posts")
        return 0

    # Claim IDs before Discord send so overlapping runners don't double-post.
    state.remember_ids(source_id, [p["id"] for p in new_posts])
    state.save()

    webhook = webhook_for(source)
    sent = 0
    for post in new_posts:
        embed = tweet_embed(post, int(source.get("color") or 3447003))
        print(f"[{source_id}] new post {post['id']}: {(post.get('text') or '')[:80]!r}")
        if dry_run:
            continue
        try:
            send_webhook(
                webhook,
                embeds=[embed],
                username=f"{(post.get('author') or {}).get('name') or handle}",
                avatar_url=(post.get("author") or {}).get("avatar_url"),
            )
            sent += 1
        except Exception:
            # Keep ID claimed to avoid duplicates; log and continue.
            print(f"[{source_id}] send failed for {post['id']}", file=sys.stderr)
            traceback.print_exc()

    print(f"[{source_id}] sent {sent}/{len(new_posts)}")
    return sent


def process_youtube_live(
    source: dict[str, Any],
    state: StateStore,
    dry_run: bool,
) -> int:
    source_id = source["id"]
    handle = source["handle"]
    live = check_live(handle, source.get("channel_id"))

    if not state.is_initialized(source_id):
        state.set_active_live(source_id, live["video_id"] if live else None)
        if live:
            state.remember_ids(source_id, [live["video_id"]])
        state.mark_initialized(source_id)
        print(
            f"[{source_id}] initialized "
            f"(live={live['video_id'] if live else 'no'}; no send)"
        )
        return 0

    active = state.get_active_live(source_id)
    if not live:
        if active:
            print(f"[{source_id}] live ended ({active})")
            state.set_active_live(source_id, None)
        else:
            print(f"[{source_id}] not live")
        return 0

    video_id = live["video_id"]
    if video_id == active or video_id in state.seen_ids(source_id):
        state.set_active_live(source_id, video_id)
        print(f"[{source_id}] already notified for {video_id}")
        return 0

    print(f"[{source_id}] LIVE {video_id}: {live.get('title')!r}")
    if not dry_run:
        send_webhook(
            webhook_for(source),
            content="@everyone" if source.get("mention_everyone") else None,
            embeds=[youtube_live_embed(live, int(source.get("color") or 16711680))],
            username="YouTube Live",
        )
    state.remember_ids(source_id, [video_id])
    state.set_active_live(source_id, video_id)
    return 0 if dry_run else 1


def run(config_path: Path, dry_run: bool = False, only: str | None = None) -> int:
    load_dotenv(ROOT / ".env")
    cfg = load_config(config_path)
    state = StateStore(ROOT / cfg.get("state_path", "data/state.json"), int(cfg.get("max_seen_ids") or 200))

    failures = 0
    sent_total = 0
    sources = list(cfg.get("sources") or [])
    # Limbus first: highest priority for near-real-time.
    sources.sort(key=lambda s: 0 if s.get("id") == "limbus" else 1)

    for index, source in enumerate(sources):
        if only and source.get("id") != only and source.get("handle") != only:
            continue
        if index and source.get("type") == "x":
            # Small gap so FxTwitter is less likely to 404 a burst of accounts.
            time.sleep(float(cfg.get("source_delay_seconds") or 1.5))
        try:
            if source.get("type") == "x":
                sent_total += process_x(source, cfg, state, dry_run)
            elif source.get("type") == "youtube_live":
                sent_total += process_youtube_live(source, state, dry_run)
            else:
                print(f"[{source.get('id')}] unknown type {source.get('type')}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[{source.get('id')}] ERROR: {exc}", file=sys.stderr)
            traceback.print_exc()

    state.save()
    print(f"done: sent={sent_total} failures={failures}")
    # Soft-fail: next cron minute will retry. Don't red-fail the whole Action
    # for transient FxTwitter blips.
    if failures:
        print("soft-fail: transient source errors ignored for exit code")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Relay X posts and YouTube lives to Discord")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config.json"),
        help="Path to config.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and update state logic, but do not call Discord",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Run only one source id or handle (e.g. limbus)",
    )
    args = parser.parse_args(argv)
    return run(Path(args.config), dry_run=args.dry_run, only=args.only)


if __name__ == "__main__":
    raise SystemExit(main())
