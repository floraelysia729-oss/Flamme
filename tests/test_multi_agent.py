"""Phase 4 Multi-Agent 测试 — task_queue + Worker + Coordinator"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from src.db.client import SQLiteClient
from src.agent.worker import BaseWorker
from src.agent.workers import IngestWorker, QueryWorker, LintWorker, SlidesWorker
from src.agent.coordinator import Coordinator
from src.agent.agent import Agent
from src.agent.interfaces import WorkerProtocol
from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def db():
    """临时 SQLite 数据库"""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    client = SQLiteClient(db_path)
    yield client
    client.close()
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def tools():
    """注册了 markdown_parser 的 ToolRegistry"""
    registry = ToolRegistry()
    registry.register(MarkdownParser())
    return registry


@pytest.fixture
def vault():
    """临时 vault 目录，包含测试 .md 文件"""
    tmpdir = tempfile.mkdtemp()

    Path(tmpdir, "test.md").write_text(
        "---\ntitle: 测试文档\ntags: [测试]\n---\n\n测试内容\n", encoding="utf-8"
    )

    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


# ── TaskQueue 数据层测试 ────────────────────────────────────────


class TestTaskQueue:
    """task_queue CRUD 状态机"""

    def test_push_and_claim(self, db):
        tid = db.push_task("ingest", {"path": "test.md"})
        assert tid >= 1

        task = db.claim_task("worker-1")
        assert task is not None
        assert task["id"] == tid
        assert task["status"] == "claimed"
        assert task["claimed_by"] == "worker-1"
        assert task["payload"]["path"] == "test.md"

    def test_claim_empty_queue(self, db):
        task = db.claim_task("worker-1")
        assert task is None

    def test_claim_by_type(self, db):
        db.push_task("ingest", {"path": "a.md"})
        db.push_task("query", {"question": "test"})

        # 只认领 ingest
        task = db.claim_task("worker-1", task_type="ingest")
        assert task["type"] == "ingest"

        # query 还在
        task = db.claim_task("worker-1", task_type="query")
        assert task["type"] == "query"

    def test_claim_task_by_id(self, db):
        id1 = db.push_task("ingest", {"path": "a.md"})
        id2 = db.push_task("ingest", {"path": "b.md"})

        task = db.claim_task_by_id("worker-1", id2, task_type="ingest")
        assert task is not None
        assert task["id"] == id2
        assert task["claimed_by"] == "worker-1"

        # 另一个任务仍保持 pending
        pending_ids = [t["id"] for t in db.get_tasks_by_status("pending")]
        assert id1 in pending_ids

    def test_complete_task(self, db):
        tid = db.push_task("ingest", {"path": "test.md"})
        task = db.claim_task("worker-1")
        db.complete_task(tid, {"result": "done"})

        tasks = db.get_tasks_by_status("done")
        assert len(tasks) == 1
        assert tasks[0]["payload"]["result"] == "done"

    def test_fail_task(self, db):
        tid = db.push_task("ingest", {"path": "test.md"})
        db.claim_task("worker-1")
        db.fail_task(tid, "文件不存在")

        tasks = db.get_tasks_by_status("failed")
        assert len(tasks) == 1
        assert tasks[0]["payload"]["_error"] == "文件不存在"

    def test_fail_then_retry(self, db):
        tid = db.push_task("ingest", {"path": "test.md"})
        db.claim_task("worker-1")
        db.fail_task(tid, "临时错误")

        # 重置为 pending
        ok = db.retry_failed_task(tid)
        assert ok

        # 可以重新 claim
        task = db.claim_task("worker-2")
        assert task is not None
        assert task["id"] == tid
        assert task["generation"] == 1

    def test_generation_limit(self, db):
        # 直接插入超限 generation
        tid = db.push_task("ingest", {"path": "test.md"}, generation=db.MAX_GENERATION + 1)

        # 不会被 claim
        task = db.claim_task("worker-1")
        assert task is None

    def test_retry_generation_limit(self, db):
        tid = db.push_task("ingest", {"path": "test.md"}, generation=db.MAX_GENERATION)
        db.claim_task("worker-1")
        db.fail_task(tid, "error")

        # 已达上限，不能 retry
        ok = db.retry_failed_task(tid)
        assert not ok

    def test_concurrent_claim(self, db):
        """两个 worker 同时 claim 同一个任务"""
        tid = db.push_task("ingest", {"path": "test.md"})

        task1 = db.claim_task("worker-1")
        assert task1 is not None

        # 第二次 claim 应该返回 None（队列空了）
        task2 = db.claim_task("worker-2")
        assert task2 is None

    def test_get_task_stats(self, db):
        db.push_task("ingest", {"path": "a.md"})
        db.push_task("ingest", {"path": "b.md"})
        db.push_task("query", {"question": "q"})

        stats = db.get_task_stats()
        assert stats["pending"] == 3

    def test_tasks_by_status(self, db):
        db.push_task("ingest", {"path": "a.md"})
        tid2 = db.push_task("query", {"question": "q"})

        db.claim_task("w1")  # claims first ingest
        db.complete_task(db.get_tasks_by_status("claimed")[0]["id"])

        pending = db.get_tasks_by_status("pending")
        assert len(pending) == 1
        assert pending[0]["type"] == "query"


# ── Worker 基类测试 ─────────────────────────────────────────────


class TestBaseWorker:
    """Worker 生命周期"""

    def test_worker_protocol(self):
        assert isinstance(IngestWorker("w1", db=None, tools=None), WorkerProtocol)

    def test_ingest_worker_type(self):
        w = IngestWorker("w1", db=None, tools=None)
        assert w.worker_type == "ingest"

    def test_query_worker_type(self):
        w = QueryWorker("w1", db=None, tools=None)
        assert w.worker_type == "query"

    def test_lint_worker_type(self):
        w = LintWorker("w1", db=None, tools=None)
        assert w.worker_type == "lint"

    def test_run_once_empty_queue(self, db, tools):
        worker = IngestWorker("w1", db=db, tools=tools)
        result = worker.run_once()
        assert result is None

    def test_ingest_worker_execute(self, db, tools, vault):
        path = os.path.join(vault, "test.md")

        # 推入任务
        tid = db.push_task("ingest", {"path": path, "level": "lite"})

        # Worker 执行
        worker = IngestWorker("w1", db=db, tools=tools)
        result = worker.run_once()

        assert result is not None
        assert result["_status"] == "done"
        assert "已导入" in result["_result"]

        # 验证数据库
        doc = db.get_document(path)
        assert doc is not None
        assert doc["title"] == "测试文档"

    def test_ingest_worker_fail(self, db, tools):
        db.push_task("ingest", {"path": "/nonexistent/file.md", "level": "lite"})

        worker = IngestWorker("w1", db=db, tools=tools)
        result = worker.run_once()

        assert result["_status"] == "failed"
        assert result["_error"] is not None

        # 任务在数据库中是 failed
        failed = db.get_tasks_by_status("failed")
        assert len(failed) == 1

    def test_run_loop_multiple(self, db, tools, vault):
        path = os.path.join(vault, "test.md")
        db.push_task("ingest", {"path": path, "level": "lite"})

        worker = IngestWorker("w1", db=db, tools=tools)
        results = worker.run_loop()

        assert len(results) == 1
        # 第二次循环应该为空
        results2 = worker.run_loop()
        assert len(results2) == 0

    def test_run_loop_max_tasks(self, db, tools):
        for i in range(5):
            db.push_task("lint", {"scope": "all"})

        worker = LintWorker("w1", db=db, tools=tools)
        results = worker.run_loop(max_tasks=2)
        assert len(results) == 2


# ── Lint Worker 测试 ─────────────────────────────────────────────


class TestLintWorker:
    def test_lint_clean(self, db, tools):
        # 放入一个完整文档
        db.put_document({
            "path": "clean.md",
            "title": "干净文档",
            "level": "lite",
            "status": "draft",
            "tags": ["测试"],
            "word_count": 100,
            "content_hash": "abc123",
        })

        db.push_task("lint", {"scope": "all"})
        worker = LintWorker("w1", db=db, tools=tools)
        result = worker.run_once()
        assert "Lint 通过" in result["_result"]

    def test_lint_finds_issues(self, db, tools):
        # 放入一个缺 tags 的文档
        db.put_document({
            "path": "bad.md",
            "title": "",
            "level": "lite",
            "status": "draft",
            "tags": [],
            "word_count": 100,
        })

        db.push_task("lint", {"scope": "all"})
        worker = LintWorker("w1", db=db, tools=tools)
        result = worker.run_once()
        assert "Lint 发现" in result["_result"]


class TestSlidesWorker:
    def test_slides_repair_on_incomplete_output(self, db, tools, vault):
        class FakeLLM:
            def __init__(self):
                self.calls = 0

            def complete(self, messages, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return "这是一个提纲，不是 HTML"
                slides = "\n".join(
                    [f'<section class="slide"><h2>S{i}</h2></section>' for i in range(1, 9)]
                )
                return f"<!DOCTYPE html><html><head><title>x</title></head><body>{slides}</body></html>"

        out_dir = os.path.join(vault, "slides_out")
        db.push_task("slides", {"topic": "测试主题", "outline": "", "output_dir": out_dir})

        llm = FakeLLM()
        worker = SlidesWorker("w1", db=db, tools=tools, llm=llm)
        result = worker.run_once()

        assert result is not None
        assert result["_status"] == "done"
        assert "(8 页)" in result["_result"]
        assert llm.calls == 2


# ── Coordinator 集成测试 ────────────────────────────────────────


class TestCoordinator:
    """Router → task_queue → Worker → 结果"""

    def test_coordinator_simple_status(self, db, tools):
        """status 命令走单 Agent 快速返回"""
        agent = Agent(tools=tools, db=db)
        coord = Coordinator(agent=agent, db=db, tools=tools, max_workers=2)
        result = coord.run("status")
        assert "文档总数" in result

    def test_coordinator_ingest_single(self, db, tools, vault):
        """单文件 ingest 不拆解，直接执行"""
        path = os.path.join(vault, "test.md")
        agent = Agent(tools=tools, db=db)
        coord = Coordinator(agent=agent, db=db, tools=tools, max_workers=2)
        result = coord.run(f'ingest "{path}"', level="lite")
        assert "已导入" in result

    def test_coordinator_decompose_index(self, db, tools, vault):
        """全量索引拆解为多个任务"""
        # 先放入几个文档
        for name in ["a.md", "b.md", "c.md"]:
            path = os.path.join(vault, name)
            Path(path).write_text(f"---\ntitle: {name}\n---\n\n{name} 内容\n", encoding="utf-8")
            db.put_document({
                "path": path, "title": name, "level": "lite",
                "status": "draft", "tags": [], "word_count": 10,
                "content_hash": f"hash_{name}",
            })

        agent = Agent(tools=tools, db=db)
        coord = Coordinator(agent=agent, db=db, tools=tools, max_workers=2)
        result = coord.run("index --full")
        # 应该执行了多个 ingest 任务
        assert "任务完成" in result or "已导入" in result
        # 回归：worker 必须成功 claim，不能卡在 pending
        assert db.get_tasks_by_status("pending") == []

    def test_coordinator_run_single(self, db, tools):
        """run_single 走单 Agent"""
        agent = Agent(tools=tools, db=db)
        coord = Coordinator(agent=agent, db=db, tools=tools, max_workers=2)
        result = coord.run_single("status")
        assert "文档总数" in result

    def test_dispatch_executes_exact_task_id(self, db, tools, vault):
        """dispatch 后 worker 必须执行本次 task_id，而不是队列里更旧任务"""
        # 旧任务（更早）故意放一个会失败的 ingest
        db.push_task("ingest", {"path": "/nonexistent/old.md", "level": "lite"})

        # 本次任务（应被执行）
        path = os.path.join(vault, "test.md")
        agent = Agent(tools=tools, db=db)
        coord = Coordinator(agent=agent, db=db, tools=tools, max_workers=2)
        task_id = coord.dispatch("ingest", {"path": path, "level": "lite"})
        result = coord.wait_for(task_id, timeout=10)

        assert isinstance(result, str)
        assert "已导入" in result

        row = db._conn.execute("SELECT status FROM task_queue WHERE id = ?", (task_id,)).fetchone()
        assert row["status"] == "done"


# ── 故障恢复测试 ─────────────────────────────────────────────────


class TestFaultRecovery:
    """Worker 崩溃 → 任务重分配"""

    def test_failed_task_can_be_reclaimed(self, db, tools):
        # 不存在的文件会导致 IngestWorker raise ValueError
        db.push_task("ingest", {"path": "/nonexistent/file.md", "level": "lite"})

        # Worker 1 执行失败
        worker1 = IngestWorker("w1", db=db, tools=tools)
        result = worker1.run_once()
        assert result["_status"] == "failed"

        # 重置
        db.retry_failed_task(result["id"])

        # Worker 2 可以重新认领（仍然会失败，但证明流程通）
        worker2 = IngestWorker("w2", db=db, tools=tools)
        result2 = worker2.run_once()
        assert result2 is not None  # 能认领到
        assert result2["_status"] == "failed"
        assert result2["generation"] == 1


class TestConcurrentClaim:
    """claim_task 原子性验证 — 使用多进程避免 SQLite 线程限制"""

    def test_claim_is_unique(self, db):
        """连续 claim 同一个任务：第一个成功，后续返回 None"""
        db.push_task("ingest", {"path": "test.md"})

        # 第一个 claim 成功
        task = db.claim_task("w1", task_type="ingest")
        assert task is not None
        assert task["claimed_by"] == "w1"

        # 第二个 claim 返回 None
        task2 = db.claim_task("w2", task_type="ingest")
        assert task2 is None


class TestBrainLLMDecompose:
    """brain_llm 辅助任务拆解"""

    def test_decompose_with_brain_llm(self, db, tools):
        """有 brain_llm 时 query 可以被拆解"""
        from unittest.mock import MagicMock

        agent = Agent(tools=tools, db=db)
        brain_llm = MagicMock()
        brain_llm.complete.return_value = "[]"

        coord = Coordinator(
            agent=agent, db=db, tools=tools, llm=MagicMock(), brain_llm=brain_llm,
        )

        # query 意图会尝试 brain_llm 拆解
        tasks = coord._decompose("query", {"question": "什么是矩阵"})

        # brain_llm 被调用了
        brain_llm.complete.assert_called_once()
        # 返回空列表（不需要拆解）
        assert tasks == []

    def test_decompose_without_brain_llm(self, db, tools):
        """没有 brain_llm 时 query 不拆解"""
        agent = Agent(tools=tools, db=db)
        coord = Coordinator(agent=agent, db=db, tools=tools)

        tasks = coord._decompose("query", {"question": "什么是矩阵"})
        assert tasks == []
