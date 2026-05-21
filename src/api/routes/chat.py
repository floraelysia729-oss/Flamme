"""POST /api/chat — SSE 流式输出（通过 Orchestrator）"""

import json
import uuid
import threading
import queue as queue_mod
import logging
from typing import Generator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.deps import get_request_config, build_llm_from_config, build_brain_llm_from_config, get_config, get_request_config_or_default
from src.config import Config


router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    agent: str | None = None
    session_id: str | None = None
    mode: str = "search"
    selected_files: list[str] | None = None


def _build_thread_orchestrator(cfg: Config, llm, brain_llm):
    """在 producer 线程中构建独立的 Orchestrator（每个线程独立 SQLite 连接）"""
    from src.db.client import SQLiteClient
    from src.db.conversation import ConversationStore
    from src.tools.embedding_store import EmbeddingStore
    from src.tools.bootstrap import build_registry
    from src.agent.orchestrator import Orchestrator
    from src.agent.coordinator import Coordinator
    from src.agent.agent import Agent
    from src.llm.queue import LLMQueue

    emb = EmbeddingStore(cfg.embeddings_dir, dim=cfg.embed_dim)
    llm_queue = LLMQueue(max_concurrency=cfg.max_concurrency) if llm else None

    # 每个线程独立的 SQLite 连接
    db = SQLiteClient(cfg.db_path, vault_path=cfg.vault_path)
    conv_store = ConversationStore(cfg.conversations_db)

    # 共享工具注册（单一来源）
    registry = build_registry(cfg, db, llm=llm, embedding_store=emb)

    orchestrator_llm = brain_llm or llm
    agent = Agent(tools=registry, db=db, llm=llm, embedding_store=emb, llm_queue=llm_queue)
    coordinator = Coordinator(
        agent=agent, db=db, tools=registry,
        llm=llm, brain_llm=brain_llm,
        embedding_store=emb, llm_queue=llm_queue,
    )
    return Orchestrator(
        brain_llm=orchestrator_llm,
        tool_registry=registry,
        coordinator=coordinator,
        conversation_store=conv_store,
        vault_path=cfg.vault_path,
    )


def _sse_stream(question: str, session_id: str, cfg: Config,
                mode: str = "search",
                selected_files: list[str] | None = None) -> Generator[str, None, None]:
    """生成 SSE 事件流 — producer 线程独立连接"""
    import time

    llm = build_llm_from_config(cfg)
    brain_llm = build_brain_llm_from_config(cfg)
    if not (brain_llm or llm):
        yield f"data: {json.dumps({'type': 'error', 'content': 'LLM 未配置。请在插件设置中填写 API Key。'}, ensure_ascii=False)}\n\n"
        return
    if not brain_llm:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Orchestrator 需要 Brain API Key。请在插件设置中配置 LLM API Key。'}, ensure_ascii=False)}\n\n"
        return

    token_queue = queue_mod.Queue()
    t0 = time.time()

    def producer():
        try:
            orchestrator = _build_thread_orchestrator(cfg, llm, brain_llm)
            for token in orchestrator.chat(session_id, question, mode=mode, selected_files=selected_files):
                token_queue.put(token)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.exception("SSE producer failed: %s", e)
            token_queue.put(f"__ERROR__{type(e).__name__}: {e}\n{tb}")
        finally:
            token_queue.put(None)

    thread = threading.Thread(target=producer, daemon=True)
    thread.start()

    try:
        while True:
            try:
                token = token_queue.get(timeout=1)
            except queue_mod.Empty:
                # 长任务期间维持 SSE 连接，避免 120s 无事件被误判为失败
                yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
                continue
            if token is None:
                break
            if isinstance(token, dict):
                if token.get("__type__") == "suggested_questions":
                    yield f"data: {json.dumps({'type': 'suggested_questions', 'questions': token['questions']}, ensure_ascii=False)}\n\n"
                continue
            if isinstance(token, str) and token.startswith("__ERROR__"):
                yield f"data: {json.dumps({'type': 'error', 'content': token[9:]}, ensure_ascii=False)}\n\n"
                break
            if isinstance(token, str) and token.startswith("\n> 🔧"):
                yield f"data: {json.dumps({'type': 'tool_call', 'content': token.strip()}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        logger.exception("SSE stream failed: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    cfg = get_request_config(request)
    session_id = req.session_id or str(uuid.uuid4())
    return StreamingResponse(
        _sse_stream(req.message, session_id, cfg, mode=req.mode, selected_files=req.selected_files),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.delete("/chat/{session_id}")
async def clear_session(session_id: str, request: Request):
    """清空会话历史"""
    from src.db.conversation import ConversationStore
    cfg = get_request_config_or_default(request)
    conv_store = ConversationStore(cfg.conversations_db)
    conv_store.clear_session(session_id)
    return {"ok": True}


@router.get("/chat/sessions")
async def list_sessions(request: Request):
    """返回会话列表"""
    from src.db.conversation import ConversationStore
    cfg = get_request_config_or_default(request)
    conv_store = ConversationStore(cfg.conversations_db)
    sessions = conv_store.list_sessions()
    conv_store.close()
    return {"sessions": sessions}


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """获取单个会话消息"""
    from src.db.conversation import ConversationStore
    cfg = get_request_config_or_default(request)
    conv_store = ConversationStore(cfg.conversations_db)
    messages = conv_store.get_session_messages(session_id)
    conv_store.close()
    return {"session_id": session_id, "messages": messages}
