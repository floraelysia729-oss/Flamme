"""摄入路由 — 单文件 + 全量扫描 + 同步索引"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.api.deps import get_request_config_or_default
from src.api.runtime import build_coordinator, build_db, build_tools
from src.tools.sync import run_vault_sync


router = APIRouter(prefix="/ingest")


class IngestRequest(BaseModel):
    path: str
    level: str = "lite"


class IngestVaultRequest(BaseModel):
    level: str = "lite"


class SyncRequest(BaseModel):
    embed: bool = False
    graph: bool = False


@router.post("")
def ingest_file(req: IngestRequest, request: Request):
    cfg = get_request_config_or_default(request)
    runtime = build_coordinator(cfg)
    db = runtime["db"]
    coordinator = runtime["coordinator"]
    try:
        task_id = coordinator.dispatch("ingest", {"path": req.path, "level": req.level})
        result = coordinator.wait_for(task_id, timeout=600)
        if isinstance(result, dict) and result.get("error"):
            return {"status": "error", "result": result}
        return {"status": "ok", "result": result}
    finally:
        db.close()


@router.post("/vault")
def ingest_vault(request: Request):
    cfg = get_request_config_or_default(request)
    db = build_db(cfg)
    try:
        data = run_vault_sync(db, cfg.vault_path)
        if data.get("error"):
            return {"status": "error", "error": data["error"]}
        return {"status": "ok", **data}
    finally:
        db.close()


@router.post("/sync")
def sync_vault(req: SyncRequest, request: Request):
    """同步 vault 文件到 SQLite 索引"""
    cfg = get_request_config_or_default(request)
    runtime = build_tools(cfg)
    db = runtime["db"]
    registry = runtime["registry"]
    try:
        data = run_vault_sync(
            db, cfg.vault_path, registry,
            embed=req.embed, graph=req.graph,
        )
        if data.get("error"):
            return {"status": "error", "error": data["error"]}
        return {"status": "ok", **data}
    finally:
        db.close()
