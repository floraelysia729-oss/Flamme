"""状态路由 — 统计信息"""

from fastapi import APIRouter, Request

from src.api.deps import get_request_config_or_default

router = APIRouter(prefix="/status")


@router.get("")
def get_status(request: Request):
    from src.db.client import SQLiteClient

    cfg = get_request_config_or_default(request)
    db = SQLiteClient(cfg.db_path, vault_path=cfg.vault_path)
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
    }
