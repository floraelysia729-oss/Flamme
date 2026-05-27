"""Wiki tools tests."""

import os
import shutil
import tempfile

from src.db.client import SQLiteClient
from src.tools.wiki_ops import WikiCreatePageTool


def test_wiki_create_page_persists_document_with_valid_level():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault, exist_ok=True)

    db = SQLiteClient(db_path)
    tool = WikiCreatePageTool(db=db, vault_path=vault)

    try:
        result = tool.execute({
            "title": "测试主题页",
            "type": "topic",
            "content": "这里是正文",
            "tags": ["测试"],
            "related": [],
        })
        assert not result.is_error
        assert result.data.get("created") is True
        rel_path = result.data["path"].replace("\\", "/")
        assert "/topics/" in rel_path or rel_path.startswith("topics/")
        assert ".flamme" not in rel_path

        doc = db.get_document(result.data["path"])
        assert doc is not None
        assert doc["title"] == "测试主题页"
        assert doc["level"] == "pro"
    finally:
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
