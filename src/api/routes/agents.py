"""Agent 路由 — 列表 + SSE 流式聊天"""

import json
from typing import Generator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.deps import get_request_config_or_default, build_llm_from_config

router = APIRouter(prefix="/agents")


class AgentChatRequest(BaseModel):
    message: str


def _agent_sse_stream(name: str, question: str, cfg) -> Generator[str, None, None]:
    from src.api.agent_registry import AgentRegistry
    from src.db.client import SQLiteClient
    from src.tools.embedding_store import EmbeddingStore
    from src.tools.bootstrap import build_registry
    from src.llm.queue import LLMQueue

    db = SQLiteClient(cfg.db_path, vault_path=cfg.vault_path)
    emb = EmbeddingStore(cfg.embeddings_dir, dim=cfg.embed_dim)
    llm = build_llm_from_config(cfg)
    queue = LLMQueue(max_concurrency=cfg.max_concurrency) if llm else None
    tools = build_registry(cfg, db, llm=llm, embedding_store=emb)
    registry = AgentRegistry(db, tools, emb, llm, queue)
    agent = registry.get_agent(name)
    try:
        for token in agent.stream_query(question):
            yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"


@router.get("")
def list_agents(request: Request):
    from src.api.agent_registry import AgentRegistry
    from src.db.client import SQLiteClient
    from src.tools.embedding_store import EmbeddingStore
    from src.tools.bootstrap import build_registry
    from src.llm.queue import LLMQueue

    cfg = get_request_config_or_default(request)
    db = SQLiteClient(cfg.db_path, vault_path=cfg.vault_path)
    emb = EmbeddingStore(cfg.embeddings_dir, dim=cfg.embed_dim)
    llm = build_llm_from_config(cfg)
    queue = LLMQueue(max_concurrency=cfg.max_concurrency) if llm else None
    tools = build_registry(cfg, db, llm=llm, embedding_store=emb)
    registry = AgentRegistry(db, tools, emb, llm, queue)
    return {"agents": registry.list_agents()}


@router.post("/{name}/chat")
async def agent_chat(name: str, req: AgentChatRequest, request: Request):
    cfg = get_request_config_or_default(request)
    return StreamingResponse(
        _agent_sse_stream(name, req.message, cfg),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
