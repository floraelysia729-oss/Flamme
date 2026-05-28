"""Vault 同步基线 — 记录上次成功 run 时的 git commit

存储于 .wiki/sync_baseline.json，供 plan 计算「自上次同步以来的变更」。
与 UI 框架无关，Tauri / Obsidian / CLI 共用。
"""

import json
from datetime import datetime, timezone
from pathlib import Path


BASELINE_FILENAME = "sync_baseline.json"


def baseline_path(wiki_dir: str) -> Path:
    return Path(wiki_dir) / BASELINE_FILENAME


def load_baseline(wiki_dir: str) -> dict | None:
    path = baseline_path(wiki_dir)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_baseline(wiki_dir: str, *, git_commit: str | None, preset: str, summary: dict) -> dict:
    data = {
        "git_commit": git_commit,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "preset": preset,
        "summary": summary,
    }
    path = baseline_path(wiki_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
