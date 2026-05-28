"""Vault 运维 API — 与 Obsidian 解耦，Tauri / CLI / 插件共用

  GET  /api/vault/status  — git + baseline + DB 概览
  GET  /api/vault/plan    — 待处理清单（scope=all|git）
  POST /api/vault/run     — 执行预设流水线
  POST /api/vault/baseline — 手动更新同步基线（不跑任务）
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.api.deps import get_request_config_or_default
from src.api.runtime import build_coordinator, build_db
from src.vault import build_plan, build_git_info, run_vault, load_baseline, save_baseline, PRESETS
from src.infra.git_helper import GitHelper


router = APIRouter(prefix="/vault")


class VaultRunRequest(BaseModel):
    preset: str = "ingest"
    level: str | None = Field(None, description="摄入级别 raw/lite/pro，默认从路径推断")
    embed: bool = True
    graph: bool = False
    cleanup: bool = True
    scope: str = Field("all", description="all=全量扫描, git=仅 git 变更相关")


class BaselineRequest(BaseModel):
    preset: str = "manual"


@router.get("/status")
def vault_status(request: Request):
    cfg = get_request_config_or_default(request)
    db = build_db(cfg)
    try:
        git_info = build_git_info(cfg.vault_path, cfg.wiki_dir)
        baseline = load_baseline(cfg.wiki_dir)
        stats = db.get_stats()
        import os
        docs = db.list_documents()
        missing_count = sum(
            1 for d in docs
            if not os.path.isfile(os.path.join(cfg.vault_path, d["path"]))
        )
        return {
            "vault_path": cfg.vault_path,
            "git": git_info,
            "baseline": baseline,
            "db": {
                **stats,
                "missing_files": missing_count,
            },
            "presets": sorted(PRESETS),
        }
    finally:
        db.close()


@router.get("/plan")
def vault_plan(request: Request, scope: str = "all"):
    cfg = get_request_config_or_default(request)
    db = build_db(cfg)
    try:
        if scope not in ("all", "git"):
            return {"error": "scope 必须是 all 或 git"}
        return build_plan(cfg.vault_path, cfg.wiki_dir, db, scope=scope)
    finally:
        db.close()


@router.post("/run")
def vault_run(req: VaultRunRequest, request: Request):
    cfg = get_request_config_or_default(request)
    runtime = build_coordinator(cfg)
    db = runtime["db"]
    try:
        if req.scope not in ("all", "git"):
            return {"status": "error", "error": "scope 必须是 all 或 git"}
        if req.preset not in PRESETS:
            return {"status": "error", "error": f"未知 preset，可选: {sorted(PRESETS)}"}
        result = run_vault(
            cfg, db, runtime["coordinator"], runtime["registry"],
            preset=req.preset,
            level=req.level,
            embed=req.embed,
            graph=req.graph,
            cleanup=req.cleanup,
            scope=req.scope,
        )
        if result.get("error"):
            return {"status": "error", **result}
        return {"status": "ok", **result}
    finally:
        db.close()


@router.post("/baseline")
def vault_baseline(req: BaselineRequest, request: Request):
    """将当前 git HEAD 标记为已同步基线（不执行任务）"""
    cfg = get_request_config_or_default(request)
    git = GitHelper(cfg.vault_path)
    git_commit = None
    if git.is_repo():
        try:
            git_commit = git.get_head_commit()
        except RuntimeError:
            pass
    baseline = save_baseline(
        cfg.wiki_dir,
        git_commit=git_commit,
        preset=req.preset,
        summary={"manual": True},
    )
    return {"status": "ok", "baseline": baseline}
