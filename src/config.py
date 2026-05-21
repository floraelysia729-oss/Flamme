"""配置模块 — 从 .env 文件读取项目配置

多角色 LLM 配置：
  LLM_*     → 通用 chat（DeepSeek）
  EMBED_*   → 向量嵌入（千问 DashScope）
  BRAIN_*   → 多 Agent 编排大脑（GLM）
  MINERU_*  → PDF 精准解析（MinerU API）
  OCR_*     → 手写识别视觉模型（DashScope Qwen-VL）

优先级：命令行参数 > .env 文件 > 环境变量 > 自动检测 > 默认值
"""

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv, find_dotenv


def _load_dotenv():
    """加载 .env 文件（.env 优先于系统环境变量）"""
    env_path = find_dotenv(usecwd=True)
    if env_path:
        load_dotenv(env_path, override=True)


@dataclass
class Config:
    vault_path: str = ""
    # --- Chat LLM (DeepSeek) ---
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    # --- Embedding (千问 DashScope) ---
    embed_api_key: str = ""
    embed_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embed_model: str = "text-embedding-v3"
    embed_dim: int = 1024
    # --- Brain LLM (DeepSeek — 多 Agent 编排大脑) ---
    brain_api_key: str = ""
    brain_base_url: str = "https://api.deepseek.com"
    brain_model: str = "deepseek-chat"
    # --- MinerU (PDF 精准解析) ---
    mineru_api_token: str = ""
    mineru_model_version: str = "vlm"
    # --- Vision OCR (DashScope Qwen-VL — 手写识别) ---
    ocr_api_key: str = ""
    ocr_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ocr_model: str = "qwen-vl-max"
    # --- 运行时 ---
    db_path: str = ""
    max_concurrency: int = 2
    log_level: str = "INFO"

    def __post_init__(self):
        if not self.vault_path:
            self.vault_path = detect_vault()
        if not self.db_path:
            db_dir = Path(self.vault_path) / ".wiki"
            db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(db_dir / "knowledge.db")
        self._wiki_dir = str(Path(self.vault_path) / ".wiki")

    # ── 派生路径 ──
    @property
    def wiki_dir(self) -> str:
        return self._wiki_dir

    @property
    def embeddings_dir(self) -> str:
        return str(Path(self._wiki_dir) / "embeddings")

    @property
    def conversations_db(self) -> str:
        return str(Path(self._wiki_dir) / "conversations.db")

    @property
    def graph_json(self) -> str:
        return str(Path(self._wiki_dir) / "graph.json")

    @property
    def flamme_dir(self) -> str:
        """Vault 级别 .flamme/ 目录（API 生成的实体/主题页）"""
        d = Path(self.vault_path) / ".flamme"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    # ── 路径工具 ──
    def to_relpath(self, path: str) -> str:
        """绝对路径 → vault 内相对路径（正斜杠）"""
        if not path:
            return path
        p = Path(path)
        try:
            return str(p.relative_to(self.vault_path)).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")

    def to_abspath(self, relpath: str) -> str:
        """相对路径 → 绝对路径"""
        if not relpath:
            return relpath
        return str(Path(self.vault_path) / relpath.replace("\\", "/"))

    @staticmethod
    def is_source_doc(relpath: str) -> bool:
        """判断归一化后的相对路径是否属于 pro/lite/raw"""
        return (relpath.startswith("pro/") or relpath.startswith("lite/")
                or relpath.startswith("raw/"))


def detect_vault() -> str:
    """从当前目录向上查找包含 .obsidian/ 的目录。
    找不到时扫描 cwd 直接子目录，避免把项目本身误当 vault。
    """
    current = Path.cwd()
    # 1. 向上查找
    for parent in [current] + list(current.parents):
        if (parent / ".obsidian").is_dir():
            return str(parent)
    # 2. 向下扫描一层子目录
    for child in sorted(current.iterdir()):
        if child.is_dir() and (child / ".obsidian").is_dir():
            return str(child)
    # 3. 都没找到 → fallback 到 cwd（兼容无 .obsidian 的纯文件夹）
    #    API 模式下 per-request config 会通过 X-Vault-Path 覆盖，此处 warning 是噪声
    import logging
    logging.getLogger(__name__).debug(
        "未找到 .obsidian 目录，vault 将使用当前目录: %s。"
        "建议在 .env 中设置 LLM_WIKI_VAULT 指向你的 Obsidian vault。",
        current,
    )
    return str(current)


def load_config(**overrides) -> Config:
    """加载配置，合并 .env 文件、环境变量和命令行参数"""
    _load_dotenv()

    cfg = Config(
        vault_path=os.environ.get("LLM_WIKI_VAULT", ""),
        # Chat (DeepSeek)
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
        llm_model=os.environ.get("LLM_MODEL", "deepseek-chat"),
        # Embedding (千问)
        embed_api_key=os.environ.get("EMBED_API_KEY", os.environ.get("DASHSCOPE_API_KEY", "")),
        embed_base_url=os.environ.get("EMBED_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        embed_model=os.environ.get("EMBED_MODEL", "text-embedding-v3"),
        embed_dim=int(os.environ.get("EMBED_DIM", "1024")),
        # Brain (DeepSeek)
        brain_api_key=os.environ.get("BRAIN_API_KEY", os.environ.get("ZHIPU_API_KEY", "")),
        brain_base_url=os.environ.get("BRAIN_BASE_URL", "https://api.deepseek.com"),
        brain_model=os.environ.get("BRAIN_MODEL", "deepseek-chat"),
        # MinerU
        mineru_api_token=os.environ.get("MINERU_API_TOKEN", ""),
        mineru_model_version=os.environ.get("MINERU_MODEL_VERSION", "vlm"),
        # Vision OCR (fallback: 复用 embedding 的 DashScope key)
        ocr_api_key=os.environ.get("OCR_API_KEY", os.environ.get("EMBED_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))),
        ocr_base_url=os.environ.get("OCR_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ocr_model=os.environ.get("OCR_MODEL", "qwen-vl-max"),
        # Runtime
        db_path=os.environ.get("LLM_WIKI_DB", ""),
        max_concurrency=int(os.environ.get("LLM_MAX_CONCURRENCY", "2")),
        log_level=os.environ.get("LLM_LOG_LEVEL", "INFO"),
    )
    # 命令行参数覆盖
    for k, v in overrides.items():
        if v is not None and hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def config_from_headers(headers: dict, base_cfg: Config | None = None) -> Config:
    """从插件请求 headers 构建 Config（用户自带 key 模式）

    插件通过以下 header 传入配置：
      X-Vault-Path        → vault_path
      X-LLM-Key           → llm_api_key
      X-Embed-Key         → embed_api_key
      X-Brain-Key         → brain_api_key
      X-MinerU-Token      → mineru_api_token
    其他配置继承 .env 或默认值。
    """
    overrides = {}
    if headers.get("x-vault-path"):
        overrides["vault_path"] = headers["x-vault-path"]
    if headers.get("x-llm-key"):
        overrides["llm_api_key"] = headers["x-llm-key"]
    if headers.get("x-embed-key"):
        overrides["embed_api_key"] = headers["x-embed-key"]
    if headers.get("x-brain-key"):
        overrides["brain_api_key"] = headers["x-brain-key"]
    if headers.get("x-mineru-token"):
        overrides["mineru_api_token"] = headers["x-mineru-token"]

    if not overrides:
        return base_cfg or load_config()

    return load_config(**overrides)
