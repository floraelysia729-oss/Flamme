"""文档路由 — 列表、详情、搜索"""

from contextlib import contextmanager

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from src.api.deps import get_vault_context
from src.api.runtime import build_db, build_tools
from src.api.document_ops import filter_documents, paginate, read_document, search_documents

router = APIRouter(prefix="/documents")


@contextmanager
def _db_ctx(request: Request):
    ctx = get_vault_context(request)
    db = build_db(ctx.config)
    try:
        yield ctx, db
    finally:
        db.close()


@contextmanager
def _tools_ctx(request: Request):
    ctx = get_vault_context(request)
    bundle = build_tools(ctx.config)
    try:
        yield ctx, bundle["db"], bundle["registry"]
    finally:
        bundle["db"].close()


class DocumentListResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    per_page: int


@router.get("", response_model=DocumentListResponse)
def list_documents(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = None,
    level: str | None = None,
    tag: str | None = None,
):
    """分页列表 + 元数据关键词筛选（title/path 子串，非向量搜索）。"""
    with _db_ctx(request) as (_ctx, db):
        docs = filter_documents(db, level=level, tag=tag, search=search)
        items, total = paginate(docs, page, per_page)
        return DocumentListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/{file_path:path}")
def get_document(file_path: str, request: Request):
    """单篇详情 — 正文经 wiki_read_page（含二进制 converted 路径）。"""
    with _tools_ctx(request) as (ctx, db, registry):
        return read_document(ctx, db, registry, file_path)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("/search")
def search_documents_route(req: SearchRequest, request: Request):
    """语义/向量搜索 — 经 wiki_search（与对话内检索同路径）。"""
    with _tools_ctx(request) as (_ctx, _db, registry):
        return search_documents(registry, req.query, req.top_k)
