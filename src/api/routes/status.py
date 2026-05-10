"""状态路由 — 统计信息"""

from fastapi import APIRouter

from src.api.deps import get_db

router = APIRouter(prefix="/status")


@router.get("")
def get_status():
    db = get_db()
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
