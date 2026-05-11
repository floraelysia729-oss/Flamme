"""
LLM 工具库 — 共享的 API 调用、frontmatter 解析、内容处理

被 entity_extract.py / tag_notes.py / llm_daily.py 共用。
"""

import logging
import os
import re
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

_SCRIPT_DIR = Path(__file__).resolve().parent
_VAULT_ROOT = _SCRIPT_DIR.parent

# 自动加载 .env：从 scripts/ 向上搜索，找到第一个即用
_env = load_dotenv(_SCRIPT_DIR / ".env", override=True, verbose=False)
if not _env:
    _env = load_dotenv(_VAULT_ROOT / ".env", override=True, verbose=False)
if not _env:
    # 从 vault root 向下搜索所有 .env
    for _p in _VAULT_ROOT.rglob(".env"):
        load_dotenv(_p, override=True, verbose=False)
        break

_LOG_DIR = _SCRIPT_DIR


def setup_logging(name="llm_daily"):
    """配置文件日志，自动保留 30 天"""
    log_file = _LOG_DIR / f"{name}.log"
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # 避免重复添加 handler

    handler = TimedRotatingFileHandler(
        log_file, when="D", interval=1, backupCount=30, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


# ── API 调用 ──────────────────────────────────────────────────────────

def get_client():
    """获取 OpenAI 兼容的 LLM client"""
    try:
        from openai import Client
    except ImportError:
        print("Error: openai package not installed. Run: pip install openai")
        sys.exit(1)

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("Error: LLM_API_KEY environment variable not set")
        sys.exit(1)

    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    return Client(base_url=base_url, api_key=api_key)


def get_model():
    return os.environ.get("LLM_MODEL", "deepseek-chat")


def call_llm(client, messages, max_retries=3, max_tokens=4096, temperature=0.3):
    """调用 LLM，带重试和指数退避"""
    model = get_model()
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return resp.choices[0].message.content
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt * 2
                print(f"  [retry] API error: {e}, retry in {wait}s")
                time.sleep(wait)
            else:
                raise


# ── Frontmatter ──────────────────────────────────────────────────────

def read_frontmatter(text):
    """解析 YAML frontmatter 为字典"""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    fm = {}
    current_key = None
    current_list = []
    for line in m.group(1).split("\n"):
        if line.startswith("  - "):
            if current_key:
                current_list.append(line.strip().lstrip("- ").strip('"').strip("'"))
            continue
        if current_key and current_list:
            fm[current_key] = current_list
            current_list = []
        kv = re.match(r"^(\w+):\s*(.*)", line)
        if kv:
            current_key = kv.group(1)
            val = kv.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",") if x.strip()]
                fm[current_key] = items
                current_key = None
            elif val:
                fm[current_key] = val
                current_key = None
            else:
                current_list = []
    if current_key and current_list:
        fm[current_key] = current_list
    return fm


def strip_frontmatter(text):
    """去除 frontmatter，返回纯正文"""
    return re.sub(r"^---\n.*?\n---\n*", "", text, count=1, flags=re.DOTALL)


def extract_title(text):
    """从 frontmatter 或首个标题提取标题"""
    m = re.search(r'^title:\s*"?(.+?)"?\s*$', text, re.MULTILINE)
    if m:
        return m.group(1).strip('"')
    m = re.search(r"^# (.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""
