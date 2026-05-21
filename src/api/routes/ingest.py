"""摄入路由 — 单文件 + 全量扫描 + 同步索引"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.api.deps import get_request_config_or_default

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
    from src.api.agent_registry import AgentRegistry
    from src.api.deps import get_llm_queue as _gq
    from src.db.client import SQLiteClient
    from src.tools.embedding_store import EmbeddingStore
    from src.tools.bootstrap import build_registry
    from src.llm.provider import DefaultLLM
    from src.api.deps import build_llm_from_config, build_brain_llm_from_config

    cfg = get_request_config_or_default(request)
    db = SQLiteClient(cfg.db_path, vault_path=cfg.vault_path)
    emb = EmbeddingStore(cfg.embeddings_dir, dim=cfg.embed_dim)
    llm = build_llm_from_config(cfg)
    queue = _gq() if llm else None
    tools = build_registry(cfg, db, llm=llm, embedding_store=emb)
    registry = AgentRegistry(db, tools, emb, llm, queue)
    agent = registry.get_agent()
    result = agent.run(f'ingest "{req.path}"', level=req.level)
    return {"status": "ok", "result": result}


@router.post("/vault")
def ingest_vault(req: IngestVaultRequest, request: Request):
    from src.api.agent_registry import AgentRegistry
    from src.api.deps import get_llm_queue as _gq
    from src.db.client import SQLiteClient
    from src.tools.embedding_store import EmbeddingStore
    from src.tools.bootstrap import build_registry
    from src.api.deps import build_llm_from_config

    cfg = get_request_config_or_default(request)
    db = SQLiteClient(cfg.db_path, vault_path=cfg.vault_path)
    emb = EmbeddingStore(cfg.embeddings_dir, dim=cfg.embed_dim)
    llm = build_llm_from_config(cfg)
    queue = _gq() if llm else None
    tools = build_registry(cfg, db, llm=llm, embedding_store=emb)
    registry = AgentRegistry(db, tools, emb, llm, queue)
    agent = registry.get_agent()
    result = agent.run("scan")
    return {"status": "ok", "result": result}


@router.post("/sync")
def sync_vault(req: SyncRequest, request: Request):
    """同步 vault 文件到 SQLite 索引"""
    from src.tools.sync import SyncTool
    from src.db.client import SQLiteClient
    from src.tools.embedding_store import EmbeddingStore
    from src.tools.bootstrap import build_registry
    from src.agent.agent import Agent
    from src.llm.queue import LLMQueue
    from src.api.deps import build_llm_from_config

    cfg = get_request_config_or_default(request)
    db = SQLiteClient(cfg.db_path, vault_path=cfg.vault_path)
    sync = SyncTool(db, cfg.vault_path)
    result = sync.execute({})

    if result.is_error:
        return {"status": "error", "error": result.error}

    data = result.data

    # 可选：自动 embedding 新文件
    if req.embed and data["to_embed"]:
        emb = EmbeddingStore(cfg.embeddings_dir, dim=cfg.embed_dim)
        llm = build_llm_from_config(cfg)
        queue = LLMQueue(max_concurrency=cfg.max_concurrency) if llm else None
        tools = build_registry(cfg, db, llm=llm, embedding_store=emb)
        agent = Agent(tools=tools, db=db, llm=llm, embedding_store=emb, llm_queue=queue)
        embed_result = agent.run("index")
        data["embed_result"] = embed_result

    # 可选：重建图谱
    if req.graph:
        from src.tools.graph_builder import GraphBuilder
        tools = build_registry(cfg, db, llm=build_llm_from_config(cfg), embedding_store=EmbeddingStore(cfg.embeddings_dir, dim=cfg.embed_dim))
        gb = tools.get("graph_builder")
        if gb:
            gb_result = gb.execute({"vault_path": cfg.vault_path})
            data["graph_result"] = "rebuilt" if not gb_result.is_error else gb_result.error

    return {"status": "ok", **data}
