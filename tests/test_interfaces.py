"""接口契约测试 — 验证所有 Protocol 可被实现类通过 isinstance 检查"""

from src.tools.interfaces import Tool
from src.llm.interfaces import LLMProvider
from src.db.interfaces_kb import KnowledgeStore
from src.agent.interfaces import AgentProtocol
from src.infra.interfaces import CheckpointManager, GitHelper


# --- 最小实现类（用于验证 Protocol 兼容性）---


class _DummyTool:
    name = "dummy"
    description = "dummy tool"

    def execute(self, params: dict) -> dict:
        return {}


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


class _DummyAgent:
    def run(self, prompt: str, **kwargs) -> str:
        return ""


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


# --- 契约测试 ---


def test_tool_protocol():
    assert isinstance(_DummyTool(), Tool)


def test_llm_provider_protocol():
    assert isinstance(_DummyLLM(), LLMProvider)


def test_knowledge_store_protocol():
    assert isinstance(_DummyStore(), KnowledgeStore)


def test_agent_protocol():
    assert isinstance(_DummyAgent(), AgentProtocol)


def test_checkpoint_protocol():
    assert isinstance(_DummyCheckpoint(), CheckpointManager)


def test_git_helper_protocol():
    assert isinstance(_DummyGit(), GitHelper)


# --- 反向测试：缺少方法不应通过 ---


class _IncompleteTool:
    name = "bad"
    # 缺少 execute 和 description


def test_incomplete_tool_fails():
    assert not isinstance(_IncompleteTool(), Tool)
