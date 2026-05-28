"""Vault 运维执行 — 确定性流水线，不经过 Orchestrator"""

import logging

from src.tools.sync import run_vault_sync, format_sync_summary
from src.vault.baseline import save_baseline
from src.vault.planner import build_plan
from src.vault.scanner import infer_level_for_path
from src.infra.git_helper import GitHelper

logger = logging.getLogger(__name__)

PRESETS = frozenset({"index", "ingest", "full", "cleanup"})


def run_vault(
    cfg,
    db,
    coordinator,
    registry,
    *,
    preset: str = "ingest",
    level: str | None = None,
    embed: bool = True,
    graph: bool = False,
    cleanup: bool = True,
    scope: str = "all",
    ingest_timeout: float = 3600,
) -> dict:
    """执行 vault 运维预设，返回结果摘要并更新 sync baseline"""
    if preset not in PRESETS:
        return {"error": f"未知 preset: {preset}，可选: {sorted(PRESETS)}"}

    plan = build_plan(cfg.vault_path, cfg.wiki_dir, db, scope=scope)
    scan = plan["scan"]
    results: dict = {"preset": preset, "scope": scope, "steps": []}

    if preset == "cleanup":
        deleted = db.purge_missing()
        results["steps"].append({"step": "cleanup", "deleted": len(deleted), "paths": deleted[:50]})
        _finalize_baseline(cfg, preset, results)
        return results

    # ── 1. 清理 DB 中已删除文件的记录 ──
    if cleanup and scan.get("md_removed"):
        deleted = db.purge_missing()
        results["steps"].append({"step": "cleanup", "deleted": len(deleted)})

    # ── 2. 批量摄入二进制 ──
    binaries = scan.get("binary_unprocessed", [])
    if preset in ("ingest", "full") and binaries:
        payloads = []
        for relpath in binaries:
            lv = level or infer_level_for_path(relpath)
            payloads.append({"path": relpath, "level": lv})
        task_ids = coordinator.dispatch_batch("ingest", payloads)
        timeout = min(ingest_timeout, max(120.0, len(task_ids) * 120.0))
        batch_results = coordinator.wait_for_batch(task_ids, timeout=timeout)
        ok = sum(1 for r in batch_results if isinstance(r, dict) and "error" not in r)
        failed = len(batch_results) - ok
        results["steps"].append({
            "step": "ingest",
            "total": len(binaries),
            "ok": ok,
            "failed": failed,
            "details": batch_results[:20],
        })

    # ── 3. 同步 .md 索引 ──
    if preset in ("index", "ingest", "full"):
        do_embed = embed and preset != "cleanup"
        do_graph = graph and preset == "full"
        sync_data = run_vault_sync(
            db, cfg.vault_path, registry,
            embed=do_embed, graph=do_graph,
        )
        if sync_data.get("error"):
            results["error"] = sync_data["error"]
            return results
        results["steps"].append({
            "step": "sync",
            "summary": format_sync_summary(sync_data),
            "added": len(sync_data.get("added", [])),
            "updated": len(sync_data.get("updated", [])),
            "removed": len(sync_data.get("removed", [])),
        })
        if sync_data.get("embed_result"):
            results["steps"].append({"step": "embed", "result": sync_data["embed_result"]})
        if sync_data.get("graph_result"):
            results["steps"].append({"step": "graph", "result": sync_data["graph_result"]})

    results["plan_after"] = build_plan(cfg.vault_path, cfg.wiki_dir, db, scope=scope)
    _finalize_baseline(cfg, preset, results)
    return results


def _finalize_baseline(cfg, preset: str, results: dict) -> None:
    git_commit = None
    git = GitHelper(cfg.vault_path)
    if git.is_repo():
        try:
            git_commit = git.get_head_commit()
        except RuntimeError:
            pass
    summary = {
        "steps": [s.get("step") for s in results.get("steps", [])],
        "pending_after": results.get("plan_after", {}).get("pending_count"),
    }
    baseline = save_baseline(cfg.wiki_dir, git_commit=git_commit, preset=preset, summary=summary)
    results["baseline"] = baseline
