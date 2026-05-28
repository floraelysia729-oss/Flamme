"""Vault 运维计划 — 合并磁盘扫描、Git 变更、同步基线"""

from src.infra.git_helper import GitHelper
from src.vault.baseline import load_baseline
from src.vault.scanner import scan_vault, estimate_seconds


def _filter_by_paths(plan: dict, paths: set[str]) -> dict:
    """只保留路径命中 git 变更集合的条目"""
    if not paths:
        return plan

    def hit(p: str) -> bool:
        if p in paths:
            return True
        # 父目录变更时也命中（如 pro/课程/ 下新增文件）
        return any(p.startswith(f"{parent}/") for parent in paths if "/" in parent)

    filtered = dict(plan)
    for key in ("md_new", "md_updated", "md_removed", "binary_unprocessed", "missing_embed"):
        filtered[key] = [p for p in plan.get(key, []) if hit(p)]
    return filtered


def build_git_info(vault_path: str, wiki_dir: str) -> dict:
    git = GitHelper(vault_path)
    baseline = load_baseline(wiki_dir)

    info = {
        "is_repo": git.is_repo(),
        "head_commit": None,
        "is_clean": None,
        "working_tree": [],
        "changed_since_baseline": [],
        "baseline": baseline,
        "baseline_commit_mismatch": False,
    }

    if not git.is_repo():
        return info

    try:
        info["head_commit"] = git.get_head_commit()
        info["is_clean"] = git.is_clean()
        info["working_tree"] = [
            {"status": c.status, "path": c.path}
            for c in git.status_porcelain()
        ]
    except RuntimeError:
        info["is_repo"] = False
        return info

    if baseline and baseline.get("git_commit"):
        base_commit = baseline["git_commit"]
        if base_commit != info["head_commit"]:
            info["baseline_commit_mismatch"] = True
        try:
            info["changed_since_baseline"] = sorted(git.changed_paths_since(base_commit))
        except RuntimeError:
            info["changed_since_baseline"] = [c.path for c in git.status_porcelain()]
    else:
        info["changed_since_baseline"] = [c.path for c in git.status_porcelain()]

    return info


def build_plan(vault_path: str, wiki_dir: str, db, *, scope: str = "all") -> dict:
    """生成运维计划（不执行）

    scope:
      - all: 磁盘 vs DB 全量差异
      - git:  仅自上次 baseline 以来 git 变更相关的差异
    """
    scan = scan_vault(vault_path, db)
    git_info = build_git_info(vault_path, wiki_dir)

    if scope == "git" and git_info["is_repo"]:
        changed = set(git_info.get("changed_since_baseline", []))
        scan = _filter_by_paths(scan, changed)

    total_pending = (
        len(scan["md_new"]) + len(scan["md_updated"]) + len(scan["md_removed"])
        + len(scan["binary_unprocessed"]) + len(scan["missing_embed"])
    )

    return {
        "scope": scope,
        "pending_count": total_pending,
        "estimate_seconds": estimate_seconds(scan),
        "scan": scan,
        "git": git_info,
        "actions": _suggest_actions(scan),
    }


def _suggest_actions(scan: dict) -> list[str]:
    actions: list[str] = []
    if scan.get("binary_unprocessed"):
        actions.append("ingest")
    if scan.get("md_new") or scan.get("md_updated"):
        actions.append("sync")
    if scan.get("md_removed"):
        actions.append("cleanup")
    if scan.get("missing_embed"):
        actions.append("embed")
    if not actions:
        actions.append("none")
    return actions
