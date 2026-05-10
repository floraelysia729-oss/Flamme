"""Agent 注册表 — 从 agents.yaml 加载配置，按 type 实例化不同 Agent 子类"""

from pathlib import Path
from yaml import safe_load

from src.agent.agent import Agent
from src.tools.registry import ToolRegistry
from src.tools.embedding_store import EmbeddingStore
from src.db.client import SQLiteClient


AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"

# type 字段 → Agent 子类映射
AGENT_CLASSES = {
    "default": Agent,
}


class AgentRegistry:
    def __init__(self, db: SQLiteClient, tools: ToolRegistry,
                 embedding_store: EmbeddingStore, llm=None, llm_queue=None):
        self._db = db
        self._tools = tools
        self._embedding_store = embedding_store
        self._llm = llm
        self._llm_queue = llm_queue
        self._configs: dict = {}
        self._agents: dict[str, Agent] = {}
        self._load_configs()

    def _load_configs(self):
        yaml_path = AGENTS_DIR / "agents.yaml"
        if not yaml_path.exists():
            return
        data = safe_load(yaml_path.read_text(encoding="utf-8"))
        for entry in data.get("agents", []):
            self._configs[entry["name"]] = entry

    def list_agents(self) -> list[dict]:
        if not self._configs:
            return [{"name": "default", "description": "默认知识库助手",
                     "tools": [], "enabled": True, "type": "default"}]
        return [
            {"name": c["name"], "description": c.get("description", ""),
             "tools": c.get("tools", []), "enabled": c.get("enabled", True),
             "type": c.get("type", "default")}
            for c in self._configs.values()
        ]

    def get_agent(self, name: str = "default") -> Agent:
        if name not in self._agents:
            config = self._configs.get(name, {})
            agent_type = config.get("type", "default")
            agent_class = AGENT_CLASSES.get(agent_type, Agent)

            self._agents[name] = agent_class(
                tools=self._tools, db=self._db, llm=self._llm,
                embedding_store=self._embedding_store,
                llm_queue=self._llm_queue,
                config=config.get("config", {}),
            )
        return self._agents[name]
