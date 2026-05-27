"""状态路由 — 统计信息"""

from fastapi import APIRouter, Request

from src.api.deps import get_vault_context
from src.api.runtime import build_db

router = APIRouter(prefix="/status")


@router.get("")
def get_status(request: Request):
    ctx = get_vault_context(request)
    db = build_db(ctx.config)
    try:
        stats = db.get_stats()
        emb_stats = db.get_embedding_stats()
        return {
            "total_documents": stats["total_documents"],
            "by_level": stats["by_level"],
            "total_tags": stats["total_tags"],
            "embeddings": {
                "embedded": emb_stats["embedded"],
                "total": emb_stats["total_documents"],
            },
            "last_updated": stats["last_updated"],
            "vault_path": ctx.vault_path,
            "vault_source": ctx.source,
            "db_path": ctx.db_path,
        }
    finally:
        db.close()
