"""EmbedIndexTool 单元测试"""

import os
import shutil
import tempfile

import numpy as np
import pytest
from unittest.mock import MagicMock

from src.db.client import SQLiteClient
from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from tests.helpers import write_md
from src.tools.embedding_store import EmbeddingStore
from src.tools.embed_index import EmbedIndexTool, embed_one


@pytest.fixture
def env():
    vault_dir = tempfile.mkdtemp()
    db_path = os.path.join(vault_dir, "test.db")
    emb_dir = os.path.join(vault_dir, "embeddings")
    db = SQLiteClient(db_path)
    emb = EmbeddingStore(emb_dir, dim=8)
    registry = ToolRegistry()
    parser = MarkdownParser()
    registry.register(parser)
    llm = MagicMock()
    llm.embed.side_effect = lambda texts: [
        np.random.randn(8).astype(np.float32).tolist() for _ in texts
    ]
    tool = EmbedIndexTool(db=db, llm=llm, embedding_store=emb, parser=parser)
    yield vault_dir, db, emb, llm, tool
    db.close()
    shutil.rmtree(vault_dir, ignore_errors=True)


def test_embed_index_batch(env):
    vault_dir, db, emb, llm, tool = env
    for i in range(3):
        path = os.path.join(vault_dir, f"doc{i}.md")
        write_md(path, f"Doc{i}", f"内容 {i}")
        db.put_document({
            "path": path,
            "title": f"Doc{i}",
            "level": "lite",
            "tags": [],
            "content_hash": f"hash_{i}",
            "word_count": 5,
        })

    result = tool.execute({"full": False})
    assert not result.is_error
    assert result.data["embedded"] == 3
    assert emb.count() == 3


def test_embed_one_skips_existing_hash(env):
    vault_dir, db, emb, llm, tool = env
    path = os.path.join(vault_dir, "a.md")
    content = "hello"
    chash = "abc123"
    db.put_document({
        "path": path, "title": "a", "level": "lite",
        "tags": [], "content_hash": chash, "word_count": 5,
    })
    ok = embed_one(db, llm, emb, path, content, chash)
    assert ok is True
    assert emb.count() == 1
    ok2 = embed_one(db, llm, emb, path, content, chash)
    assert ok2 is False
    assert llm.embed.call_count == 1
