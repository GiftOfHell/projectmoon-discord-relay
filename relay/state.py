from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, path: str | Path, max_seen_ids: int = 200) -> None:
        self.path = Path(path)
        self.max_seen_ids = max_seen_ids
        self._data: dict[str, Any] = {"sources": {}}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
            self._data.setdefault("sources", {})
        else:
            self._data = {"sources": {}}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def source(self, source_id: str) -> dict[str, Any]:
        sources = self._data["sources"]
        if source_id not in sources:
            sources[source_id] = {
                "initialized": False,
                "seen_ids": [],
                "active_live_id": None,
                "epoch": 1,
            }
        return sources[source_id]

    def is_initialized(self, source_id: str, epoch: int = 1) -> bool:
        bucket = self.source(source_id)
        return bool(bucket.get("initialized")) and int(bucket.get("epoch") or 1) == int(epoch)

    def mark_initialized(self, source_id: str, epoch: int = 1) -> None:
        bucket = self.source(source_id)
        bucket["initialized"] = True
        bucket["epoch"] = int(epoch)

    def seen_ids(self, source_id: str) -> set[str]:
        return set(self.source(source_id).get("seen_ids") or [])

    def remember_ids(self, source_id: str, ids: list[str]) -> None:
        bucket = self.source(source_id)
        merged: list[str] = []
        seen: set[str] = set()
        for item in list(ids) + list(bucket.get("seen_ids") or []):
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
            if len(merged) >= self.max_seen_ids:
                break
        bucket["seen_ids"] = merged

    def get_active_live(self, source_id: str) -> str | None:
        return self.source(source_id).get("active_live_id")

    def set_active_live(self, source_id: str, video_id: str | None) -> None:
        self.source(source_id)["active_live_id"] = video_id
