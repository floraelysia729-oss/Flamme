"""接口契约测试 — 验证所有 Protocol 可被实现类通过 isinstance 检查"""

from src.tools.interfaces import Tool, ToolResult, BaseTool
from src.llm.interfaces import LLMProvider
from src.db.interfaces_kb import KnowledgeStore
from src.agent.interfaces import WorkerProtocol
from src.infra.interfaces import CheckpointManager, GitHelper


class _DummyTool(BaseTool):
    name = "dummy"
    description = "dummy tool"

    def execute(self, params: dict) -> ToolResult:
        return ToolResult.ok({})


class _DummyLLM:
    def complete(self, messages: list[dict], **kwargs) -> str:
        return ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return []


class _DummyStore:
    def get_document(self, path: str) -> dict | None:
        return None

    def put_document(self, doc: dict) -> None:
        pass

    def delete_document(self, path: str) -> None:
        pass

    def list_documents(self, level: str | None = None) -> list[dict]:
        return []

    def get_stats(self) -> dict:
        return {}


class _DummyWorker:
    @property
    def worker_type(self) -> str:
        return "dummy"

    def execute(self, task: dict) -> str:
        return "ok"


class _DummyCheckpoint:
    def start(self, operation: str, target: str, snapshot: dict) -> int:
        return 1

    def update(self, checkpoint_id: int, snapshot: dict) -> None:
        pass

    def complete(self, checkpoint_id: int) -> None:
        pass

    def find_pending(self, operation: str) -> dict | None:
        return None


class _DummyGit:
    def get_head_commit(self) -> str:
        return "abc123"

    def commit(self, message: str) -> None:
        pass


def test_tool_protocol():
    assert isinstance(_DummyTool(), Tool)


def test_llm_provider_protocol():
    assert isinstance(_DummyLLM(), LLMProvider)


def test_knowledge_store_protocol():
    assert isinstance(_DummyStore(), KnowledgeStore)


def test_worker_protocol():
    assert isinstance(_DummyWorker(), WorkerProtocol)


def test_checkpoint_protocol():
    assert isinstance(_DummyCheckpoint(), CheckpointManager)


def test_git_helper_protocol():
    assert isinstance(_DummyGit(), GitHelper)


class _IncompleteTool:
    name = "bad"


def test_incomplete_tool_fails():
    assert not isinstance(_IncompleteTool(), Tool)
