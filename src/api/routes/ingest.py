"""摄入路由 — 单文件 + 全量扫描 + 同步索引"""

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.deps import get_db, get_tool_registry, get_embedding_store, get_llm, get_llm_queue

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
def ingest_file(req: IngestRequest):
    from src.api.deps import get_llm_queue as _gq
    from src.api.agent_registry import AgentRegistry
    db = get_db()
    tools = get_tool_registry()
    emb = get_embedding_store()
    llm = get_llm()
    queue = _gq()
    registry = AgentRegistry(db, tools, emb, llm, queue)
    agent = registry.get_agent()
    result = agent.run(f'ingest "{req.path}"', level=req.level)
    return {"status": "ok", "result": result}


@router.post("/vault")
def ingest_vault(req: IngestVaultRequest):
    from src.api.deps import get_llm_queue as _gq
    from src.api.agent_registry import AgentRegistry
    db = get_db()
    tools = get_tool_registry()
    emb = get_embedding_store()
    llm = get_llm()
    queue = _gq()
    registry = AgentRegistry(db, tools, emb, llm, queue)
    agent = registry.get_agent()
    result = agent.run("scan")
    return {"status": "ok", "result": result}


@router.post("/sync")
def sync_vault(req: SyncRequest):
    """同步 vault 文件到 SQLite 索引"""
    from src.api.deps import get_config as _gc
    from src.tools.sync import SyncTool

    cfg = _gc()
    db = get_db()
    sync = SyncTool(db, cfg.vault_path)
    result = sync.execute({})

    if result.is_error:
        return {"status": "error", "error": result.error}

    data = result.data

    # 可选：自动 embedding 新文件
    if req.embed and data["to_embed"]:
        from src.agent.agent import Agent
        tools = get_tool_registry()
        emb = get_embedding_store()
        llm = get_llm()
        queue = get_llm_queue()
        agent = Agent(tools=tools, db=db, llm=llm, embedding_store=emb, llm_queue=queue)
        embed_result = agent.run("index")
        data["embed_result"] = embed_result

    # 可选：重建图谱
    if req.graph:
        from src.tools.graph_builder import GraphBuilder
        tools = get_tool_registry()
        gb = tools.get("graph_builder")
        if gb:
            gb_result = gb.execute({"vault_path": cfg.vault_path})
            data["graph_result"] = "rebuilt" if not gb_result.is_error else gb_result.error

    return {"status": "ok", **data}
