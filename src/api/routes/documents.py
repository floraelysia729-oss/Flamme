"""文档路由 — 列表、详情、搜索"""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.api.deps import get_db

router = APIRouter(prefix="/documents")


class DocumentListResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    per_page: int


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = None,
    level: str | None = None,
    tag: str | None = None,
):
    db = get_db()
    docs = db.list_documents(level=level)
    if search:
        search_lower = search.lower()
        docs = [d for d in docs if search_lower in d.get("title", "").lower()
                or search_lower in d.get("path", "").lower()]
    if tag:
        docs = [d for d in docs if tag in d.get("tags", [])]
    total = len(docs)
    start = (page - 1) * per_page
    items = docs[start:start + per_page]
    return DocumentListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/{file_path:path}")
def get_document(file_path: str):
    db = get_db()
    doc = db.get_document(file_path)
    if not doc:
        return {"error": "not found", "path": file_path}
    # 读取正文
    content = ""
    from src.tools.markdown_parser import MarkdownParser
    from src.tools.interfaces import ToolResult
    parser = MarkdownParser()
    parsed = parser.execute({"path": db.resolve(doc["path"])})
    if isinstance(parsed, ToolResult):
        if not parsed.is_error:
            content = parsed.data.get("content", "") if isinstance(parsed.data, dict) else ""
    elif isinstance(parsed, dict) and "error" not in parsed:
        content = parsed.get("content", "")
    return {
        "path": doc["path"],
        "title": doc.get("title", ""),
        "content": content,
        "metadata": doc,
    }


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("/search")
def search_documents(req: SearchRequest):
    from src.api.deps import get_embedding_store, get_llm, get_llm_queue
    db = get_db()
    emb = get_embedding_store()
    llm = get_llm()
    if not llm or not emb or emb.count() == 0:
        return {"results": [], "message": "向量索引为空或 LLM 未配置"}
    try:
        embeddings = llm.embed([req.query])
        query_vector = embeddings[0]
        results = emb.search(query_vector, top_k=req.top_k)
        enriched = []
        for r in results:
            doc = db.get_document(r["doc_id"])
            enriched.append({
                "path": r["doc_id"],
                "title": doc["title"] if doc else r["doc_id"],
                "score": r["score"],
            })
        return {"results": enriched}
    except Exception as e:
        return {"results": [], "error": str(e)}
