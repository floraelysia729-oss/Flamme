"""Checkpoint + Git helper 测试"""

import os
import tempfile

from src.db.client import SQLiteClient
from src.infra.git_helper import GitHelper
from src.infra.checkpoint import CheckpointManager
from src.infra.interfaces import CheckpointManager as CheckpointManagerProto
from src.infra.interfaces import GitHelper as GitHelperProto


def test_git_helper_protocol():
    """GitHelper 满足 Protocol"""
    git = GitHelper(".")
    assert isinstance(git, GitHelperProto)


def test_git_get_head_commit():
    """在 git 仓库中能获取 commit hash"""
    git = GitHelper(".")
    commit = git.get_head_commit()
    assert len(commit) == 40  # SHA1 hex


def test_git_is_clean():
    git = GitHelper(".")
    # 只要不抛异常就行
    result = git.is_clean()
    assert isinstance(result, bool)


def test_checkpoint_manager_protocol():
    tmp = tempfile.mktemp(suffix=".db")
    db = SQLiteClient(tmp)
    git = GitHelper(".")
    mgr = CheckpointManager(db, git)
    assert isinstance(mgr, CheckpointManagerProto)
    db.close()
    os.unlink(tmp)


def test_checkpoint_start_and_complete():
    tmp = tempfile.mktemp(suffix=".db")
    db = SQLiteClient(tmp)
    git = GitHelper(".")
    mgr = CheckpointManager(db, git)

    cp_id = mgr.start("ingest", "test_batch", {"items": ["a.md", "b.md"]})
    assert cp_id > 0

    # 应该能找到 pending
    pending = mgr.find_pending("ingest")
    assert pending is not None
    assert pending["snapshot"]["items"] == ["a.md", "b.md"]

    # 完成
    mgr.complete(cp_id)
    assert mgr.find_pending("ingest") is None

    db.close()
    os.unlink(tmp)


def test_checkpoint_update_snapshot():
    tmp = tempfile.mktemp(suffix=".db")
    db = SQLiteClient(tmp)
    git = GitHelper(".")
    mgr = CheckpointManager(db, git)

    cp_id = mgr.start("ingest", "batch1", {"files_processed": []})
    mgr.update(cp_id, {"files_processed": ["a.md", "b.md"]})

    pending = mgr.find_pending("ingest")
    assert "a.md" in pending["snapshot"]["files_processed"]

    mgr.complete(cp_id)
    db.close()
    os.unlink(tmp)


def test_run_with_checkpoint_fresh():
    tmp = tempfile.mktemp(suffix=".db")
    db = SQLiteClient(tmp)
    git = GitHelper(".")
    mgr = CheckpointManager(db, git)

    processed_items = []

    def process(item):
        processed_items.append(item)
        return True

    result = mgr.run_with_checkpoint(
        "test_op", "batch1", ["a.md", "b.md", "c.md"], process
    )
    assert result["processed"] == 3
    assert result["failed"] == 0
    assert not result["resumed"]
    assert len(processed_items) == 3

    db.close()
    os.unlink(tmp)


def test_run_with_checkpoint_partial_failure():
    tmp = tempfile.mktemp(suffix=".db")
    db = SQLiteClient(tmp)
    git = GitHelper(".")
    mgr = CheckpointManager(db, git)

    def process(item):
        return item != "b.md"  # b.md 模拟失败

    result = mgr.run_with_checkpoint(
        "test_op", "batch1", ["a.md", "b.md", "c.md"], process
    )
    assert result["processed"] == 2
    assert result["failed"] == 1

    db.close()
    os.unlink(tmp)
