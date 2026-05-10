"""Agent 路由 — 列表 + SSE 流式聊天"""

import json
from typing import Generator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.deps import get_db, get_tool_registry, get_embedding_store, get_llm, get_llm_queue

router = APIRouter(prefix="/agents")


class AgentChatRequest(BaseModel):
    message: str


def _agent_sse_stream(name: str, question: str) -> Generator[str, None, None]:
    from src.api.agent_registry import AgentRegistry
    from src.api.deps import get_llm_queue as _gq
    db = get_db()
    tools = get_tool_registry()
    emb = get_embedding_store()
    llm = get_llm()
    queue = _gq()
    registry = AgentRegistry(db, tools, emb, llm, queue)
    agent = registry.get_agent(name)
    try:
        for token in agent.stream_query(question):
            yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"


@router.get("")
def list_agents():
    from src.api.agent_registry import AgentRegistry
    db = get_db()
    tools = get_tool_registry()
    emb = get_embedding_store()
    llm = get_llm()
    queue = get_llm_queue()
    registry = AgentRegistry(db, tools, emb, llm, queue)
    return {"agents": registry.list_agents()}


@router.post("/{name}/chat")
async def agent_chat(name: str, req: AgentChatRequest):
    return StreamingResponse(
        _agent_sse_stream(name, req.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
