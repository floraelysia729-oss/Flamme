"""API 运行时构建 — db / tools / coordinator / orchestrator 分层组装"""

from src.config import Config
from src.db.client import SQLiteClient
from src.db.conversation import ConversationStore
from src.tools.bootstrap import build_registry
from src.tools.embedding_store import EmbeddingStore
from src.llm.queue import LLMQueue
from src.agent.orchestrator import Orchestrator
from src.agent.coordinator import Coordinator
from src.api.deps import build_llm_from_config, build_brain_llm_from_config


def build_db(cfg: Config) -> SQLiteClient:
    """per-request SQLite 连接（展示读、轻量 API）"""
    return SQLiteClient(cfg.db_path, vault_path=cfg.vault_path)


def build_tools(cfg: Config) -> dict:
    """db + ToolRegistry（单工具调用：search / sync / graph build）"""
    db = build_db(cfg)
    emb = EmbeddingStore(cfg.embeddings_dir, dim=cfg.embed_dim)
    llm = build_llm_from_config(cfg)
    llm_queue = LLMQueue(max_concurrency=cfg.max_concurrency) if llm else None
    registry = build_registry(cfg, db, llm=llm, embedding_store=emb, llm_queue=llm_queue)
    return {
        "db": db,
        "registry": registry,
        "llm": llm,
        "embedding_store": emb,
        "llm_queue": llm_queue,
    }


def build_coordinator(cfg: Config) -> dict:
    """tools + Coordinator（Worker 派发，无需 Orchestrator）"""
    bundle = build_tools(cfg)
    brain_llm = build_brain_llm_from_config(cfg)
    coordinator = Coordinator(
        db=bundle["db"],
        tools=bundle["registry"],
        llm=bundle["llm"],
        brain_llm=brain_llm,
        embedding_store=bundle["embedding_store"],
        llm_queue=bundle["llm_queue"],
    )
    return {**bundle, "coordinator": coordinator}


def build_runtime(cfg: Config) -> dict:
    """完整 Agent 栈 — chat 等需要 Orchestrator 的请求"""
    bundle = build_coordinator(cfg)
    brain_llm = build_brain_llm_from_config(cfg)
    orchestrator_llm = brain_llm or bundle["llm"]
    orchestrator = Orchestrator(
        brain_llm=orchestrator_llm,
        tool_registry=bundle["registry"],
        coordinator=bundle["coordinator"],
        conversation_store=ConversationStore(cfg.conversations_db),
        vault_path=cfg.vault_path,
    )
    return {**bundle, "orchestrator": orchestrator}
