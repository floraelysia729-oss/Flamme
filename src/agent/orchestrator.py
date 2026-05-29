"""Orchestrator — deepseek 驱动的用户交互层

通过 function calling 理解用户意图，调度工具和 Worker。
替代原有的关键词路由 Router。

核心流程：
  用户消息 → deepseek 理解意图 → 调用工具/派发 Worker → 汇总结果 → 流式输出
"""

import json
import logging
import os
import queue as queue_mod
import threading
from pathlib import Path
import time
from datetime import date, datetime
from typing import AsyncGenerator

from src.tools.registry import ToolRegistry
from src.db.conversation import ConversationStore

logger = logging.getLogger(__name__)


def _safe_json_dumps(obj, **kwargs):
    """json.dumps 的安全版本，处理 date/datetime 等不可序列化对象"""
    def default(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return str(o)
    return json.dumps(obj, default=default, **kwargs)


_BINARY_EXTS = (".pdf", ".doc", ".docx", ".ppt", ".pptx")


def _is_binary_file(tc: dict) -> bool:
    """判断 tool_call 的目标文件是否为二进制格式（PDF/Word/PPT）"""
    raw_args = tc.get("arguments", "")
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except (json.JSONDecodeError, TypeError):
        return False
    path = args.get("path", "")
    return path.lower().endswith(_BINARY_EXTS)


# --- Orchestrator 可调用的工具定义（JSON Schema for function calling） ---

ORCHESTRATOR_TOOL_DEFS = [
    # --- 知识检索 ---
    {
        "type": "function",
        "function": {
            "name": "wiki_search",
            "description": "搜索知识库，返回相关页面摘要。回答知识问题的第一步。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "top_k": {"type": "integer", "description": "返回结果数", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_read_page",
            "description": "读取 wiki 页面完整内容。搜索后需要详情时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "页面标题（wikilink 名）"},
                    "path": {"type": "string", "description": "页面文件路径（备选，title 匹配不到时用 path）"}
                },
                "required": []
            }
        }
    },
    # --- 知识维护 ---
    {
        "type": "function",
        "function": {
            "name": "wiki_create_page",
            "description": "创建 wiki 实体/概念页。自动补 frontmatter。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "type": {"type": "string", "enum": ["entity", "topic", "comparison", "exploration"]},
                    "content": {"type": "string", "description": "Markdown 内容"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "related": {"type": "array", "items": {"type": "string"}, "description": "[[wikilink]]"}
                },
                "required": ["title", "type", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_update_page",
            "description": "更新已有 wiki 页面。传入 title 或 path 定位页面。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "页面标题"},
                    "path": {"type": "string", "description": "页面文件路径（title 匹配不到时用 path）"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "default": False}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "graph_query",
            "description": "查询知识图谱。search 用于搜索概念并发现关联；explore 从一个概念出发 BFS 探索子图；path 查找两个概念之间的连接路径；neighbors 查看节点的直接邻居；community 查看社区；stats 查看统计。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["search", "explore", "path", "neighbors", "community", "isolates", "stats"]},
                    "query": {"type": "string", "description": "搜索关键词（search/explore 必填）"},
                    "node": {"type": "string", "description": "节点名（neighbors 必填）"},
                    "source": {"type": "string", "description": "起始概念（path 必填）"},
                    "target": {"type": "string", "description": "目标概念（path 必填）"},
                    "community_id": {"type": "string", "description": "社区 ID（community 可选）"},
                    "depth": {"type": "integer", "description": "探索深度（explore 用，1-4，默认2）"},
                    "top_k": {"type": "integer", "description": "返回结果数（search 用，默认20）"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "entity_extract",
            "description": "从文本提取实体。发现新概念时调用。",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"]
            }
        }
    },
    # --- 全量同步 ---
    {
        "type": "function",
        "function": {
            "name": "wiki_sync",
            "description": "同步 vault 所有文件到知识库索引（扫描新增/修改/删除），可选同时生成向量索引。用户说「同步」「入库」「处理所有文件」「索引所有文件」时调用。wiki_search 返回空结果时也应主动建议调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "embed": {"type": "boolean", "default": True, "description": "是否同时生成向量索引"}
                }
            }
        }
    },
    # --- Worker 派发 ---
    {
        "type": "function",
        "function": {
            "name": "document_ingest",
            "description": "摄入文档到知识库。源文件正文不改写；PDF 转写进 .flamme/converted/；可更新 frontmatter/tags。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_lint",
            "description": "检查知识库完整性。",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["all", "frontmatter", "links", "orphans"], "default": "all"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_batch_tags",
            "description": '扫描所有缺 tags 的文档，后台自动用 LLM 补标签并写回文件。这是唯一正确的批量补标签方式。用户提到"补标签"、"缺tags"、"修复标签"、"标签缺失"时必须调用此工具，不要用 wiki_read_page 逐个读取再 wiki_update_page 逐个更新。',
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_cleanup",
            "description": '清理知识库脏数据（仅 SQLite，永不删除 vault 源文件）。purge_missing=删除 DB 中指向不存在文件的记录；purge_graph_noise=清理图谱噪声节点；status=统计。',
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["purge_missing", "purge_graph_noise", "status"],
                        "description": "purge_missing=删除文件缺失的DB记录, purge_graph_noise=清理图谱单字噪声节点, status=查看脏数据统计"
                    }
                },
                "required": ["action"]
            }
        }
    },
    # --- PDF 解析 ---
    {
        "type": "function",
        "function": {
            "name": "pdf_parse",
            "description": "解析 PDF/Word/PPT 文件为 Markdown。支持表格、公式、图片识别。返回解析后的 Markdown 内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "本地文件路径（PDF/Word/PPT）"}
                },
                "required": ["path"]
            }
        }
    },
    # --- Excalidraw OCR ---
    {
        "type": "function",
        "function": {
            "name": "excalidraw_ocr",
            "description": "识别 Excalidraw 手写笔记为 Markdown。不传 path 时自动扫描整个 vault（推荐）。传 path 处理单个文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "单个 .excalidraw.md 文件路径（可选）"},
                    "force": {"type": "boolean", "default": False, "description": "强制重新处理已有 .ocr.md 的文件"}
                }
            }
        }
    },
    # --- 术语表 ---
    {
        "type": "function",
        "function": {
            "name": "glossary",
            "description": "术语表工具。查询、定义、搜索术语，支持按领域消歧（如'梯度'在微积分和机器学习中含义不同）。处理文档前先查询术语表消歧，遇到新术语时添加定义。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["lookup", "define", "list", "search"],
                        "description": "操作类型"
                    },
                    "term": {"type": "string", "description": "术语名称"},
                    "domain": {"type": "string", "description": "所属领域（微积分/线性代数/机器学习等）"},
                    "definition": {"type": "string", "description": "术语定义"},
                    "aliases": {"type": "string", "description": "别名，逗号分隔"},
                    "seealso": {"type": "string", "description": "相关术语，逗号分隔"},
                    "source": {"type": "string", "description": "来源文档"},
                    "query": {"type": "string", "description": "搜索关键词（search 动作用）"}
                },
                "required": ["action"]
            }
        }
    },
]

# 需要派发给 Worker 的工具名
WORKER_DISPATCH = {
    "document_ingest": "ingest",
    "wiki_lint": "lint",
    "wiki_batch_tags": "batch_tag",
}

# 工具元数据 — 用于前端进度展示
# SSE 流式分级：
#   - LLM token：每轮无 tool call 时实时推送
#   - tool_status running/done：所有工具（含 Worker 派发）均有
#   - tool_status progress：仅覆写 stream_execute 的工具（如 excalidraw_ocr）
#   - Worker 派发（document_ingest 等）：走 _execute_tool_dict，阻塞等待，无中间 progress
TOOL_META = {
    "wiki_search":      {"label": "搜索知识库",   "estimate": "~2s"},
    "wiki_read_page":   {"label": "读取页面",     "estimate": "~1s"},
    "wiki_create_page": {"label": "创建页面",     "estimate": "~1s"},
    "wiki_update_page": {"label": "更新页面",     "estimate": "~1s"},
    "graph_query":      {"label": "查询图谱",     "estimate": "~2s"},
    "entity_extract":   {"label": "提取实体",     "estimate": "~3s"},
    "wiki_sync":        {"label": "同步知识库",   "estimate": "~30-60s"},
    "document_ingest":  {"label": "摄入文档",     "estimate": "~40-80s"},
    "wiki_lint":        {"label": "检查完整性",   "estimate": "~10s"},
    "wiki_batch_tags":  {"label": "批量打标签",   "estimate": "~20s"},
    "wiki_cleanup":     {"label": "清理知识库",   "estimate": "~5s"},
    "pdf_parse":        {"label": "解析 PDF",     "estimate": "~30-60s"},
    "excalidraw_ocr":   {"label": "OCR 识别",     "estimate": "~20s"},
    "glossary":         {"label": "生成术语表",   "estimate": "~10s"},
}


# ── 共享基础 prompt（所有模式共用） ──────────────────────────

BASE_PROMPT = """## 工具使用策略
- 知识问题 → wiki_search → wiki_read_page（需要详情时）
- **wiki_search 返回空 → 主动建议用户调用 wiki_sync 同步入库**
- 全量同步/入库 → wiki_sync（首次使用、添加新文件后、搜索无结果时）
- 深入了解 → graph_query 找关联
- 新概念 → entity_extract → 建议 wiki_create_page
- 摄入 Markdown/文本文件 → document_ingest
- 检查整理 → wiki_lint
- **批量补标签 → wiki_batch_tags（用户提到补标签/缺tags时，必须用此工具！）**
- **清理脏数据 → wiki_cleanup（action: purge_missing=删除文件缺失记录, purge_graph_noise=清理图谱噪声节点, status=查看统计）**
- **文件摄入/处理 → 统一用 document_ingest（支持 .md、.pdf、.doc、.docx、.ppt、.pptx 所有格式）**
  document_ingest 会自动识别文件类型：二进制文件调 MinerU 解析，Markdown 直接处理
  pdf_parse 仅用于"只想查看/预览 PDF 内容"的场景，不会入库
  用户说"处理"、"导入"、"摄入"文件时 → document_ingest

## 重要：多任务处理
当用户一次请求包含多个意图（如"搜索X并做PPT"、"查A和B的区别"）：
- 在同一轮回答中依次调用所需工具，不要只执行一个就停下
- 先用文字展示每个任务的中间结果，再继续下一个
- 每个工具调用后，继续处理后续任务，直到所有任务完成

## 源文件保护
- 源文件（.md/.pdf 等）**不可删除**，**正文不可改写**
- 允许更新源 .md 的 **frontmatter 和 tags**（用 wiki_batch_tags）
- PDF/PPT 解析结果只写入 `.flamme/converted/`，实体页写入 `entities/`

## 回答格式
- 引用来源：`> 来源：[[页面名]]`
- 概念连接用 [[wikilink]] 格式
- 操作建议：`[建实体页] [加双链] [查图谱]`

## LaTeX 公式输出规则
- 数学公式用 `$...$`（行内）或 `$$...$$`（独立行）包裹，前端会自动渲染
- 不要在公式后面再用纯文本重复写一遍公式源码
- 不要把公式放在代码块或行内代码中
- 示例：写 `$\\frac{a}{b}$` 而不是 `` `$\\frac{a}{b}$` `` 或 `a/b`
"""

# ── 模式 overlay（拼接到 BASE_PROMPT 之后） ─────────────────

SEARCH_OVERLAY = """你是 LLM-WIKI 知识库的 AI 助手。你的职责不仅是回答问题，更是主动维护和丰富知识库。

## 核心原则
1. **完整执行**：用户请求包含多个任务时，必须全部完成。例如"搜索X并做PPT"，必须先搜索并展示结果，再做PPT
2. **回答带引用**：提到知识库概念用 [[实体名]] 格式
3. **发现即行动**：缺失实体 → 提示用户创建
4. **冲突即标注**：新旧矛盾 → 明确指出
5. **结构化输出**：复杂回答用标题、列表、表格
"""

LEARN_OVERLAY = """你是学习助手。你的目标不是复述知识库内容，而是帮助用户真正理解。

## 核心原则
1. **简洁优先**：先给一段简短回答（3-5句话），让用户快速抓住重点。不要一次性输出大段内容。
2. **教学优先**：检索到的内容是你的知识锚点，但你可以补充类比、例子来帮助理解。
3. **概念连接**：主动关联知识库中的其他概念，帮助建立知识网络。
4. **引用来源**：涉及检索内容时标注 `> 来源：[[页面名]]`；你自己补充的内容不标注。

## ⚠️ 回答长度控制（最重要）
- 简单问题：3-5句话概括
- 中等问题：一小段解释 + 1个例子
- 复杂问题：给核心要点（不超过一段），然后通过追问引导深入
- 绝不要一次性输出超过一段的内容！用户可以通过追问逐步深入。

## 知识补充规则
- 检索内容为主，LLM 自己知识为辅
- 类比要贴近生活，例子要具体
- 如果检索内容不足，诚实说明，但仍然尽力用 LLM 知识帮助理解

## ⚠️ 重要：追问建议
回答结束后，你必须在最后一行输出追问建议，格式严格如下（一行）：
__SUGGESTIONS__: ["追问1", "追问2", "追问3"]
要求：
- 3 个追问，从不同角度（原理/应用/对比/延伸）
- 具体明确，不要空泛
- 难度递进
- 只在回答最后一行出现
"""


class Orchestrator:
    """用户交互层 —deepseek，负责理解意图 + 调度工具/Worker"""

    def __init__(self, brain_llm, tool_registry: ToolRegistry,
                 coordinator=None, conversation_store: ConversationStore = None,
                 vault_path: str = ""):
        self._llm = brain_llm              # deepseek
        self._tools = tool_registry         # 共享工具池
        self._coordinator = coordinator     # Worker 调度器（可选）
        self._conv = conversation_store     # 会话记忆（可选）
        self._vault_path = vault_path

    def chat(self, session_id: str, user_input: str, mode: str = "search",
             selected_files: list[str] | None = None):
        """同步版 — 返回生成器（yield token）

        mode: "search" — 知识库助手模式（默认）
              "learn"  — 学习模式（教学 prompt + 追问建议）
        selected_files: 学习模式下选中的文件路径列表，约束搜索范围
        """
        if not self._llm:
            yield "错误: LLM 未配置"
            return

        self._selected_files = set(f.replace("\\", "/") for f in selected_files) if selected_files else None
        self._selected_source_files = list(selected_files) if selected_files else None

        # 解析源文件路径到 DB 中对应的 AI 处理路径
        if selected_files and mode == "learn":
            resolved = set()
            for f in selected_files:
                f_norm = f.replace("\\", "/")
                resolved.add(f_norm)  # 源文件本身
                # 推算 .flamme/converted/ 路径
                parts = f_norm.rsplit("/", 1)
                if len(parts) == 2:
                    dir_part, file_part = parts
                    stem = file_part.rsplit(".", 1)[0] if "." in file_part else file_part
                    converted = f"{dir_part}/.flamme/converted/{stem}.md"
                    resolved.add(converted)
            self._selected_files = resolved

        # 1. 加载会话上下文
        history = []
        if self._conv:
            history = self._conv.get_messages_for_llm(session_id, n=10)

        sys_prompt = BASE_PROMPT + (LEARN_OVERLAY if mode == "learn" else SEARCH_OVERLAY)

        # 注入 vault 源文件列表，帮助 LLM 匹配模糊描述到具体路径
        file_listing = self._scan_source_files()
        if file_listing:
            sys_prompt += file_listing

        # 学习模式 + 选中文件：注入文件约束 + 预解析已转换文件
        if selected_files and mode == "learn":
            file_list = "\n".join(f"- {f}" for f in sorted(selected_files))
            converted_info = self._resolve_converted_files(selected_files)
            sys_prompt += (
                f"\n\n## 学习范围\n用户选定了以下源文件作为学习材料：\n{file_list}\n"
                f"{converted_info}"
                "优先 wiki_search 检索已有内容，不要对已转换的文件重复调用 pdf_parse 或 document_ingest。"
                "你自己补充的内容标注 `[补充]`。"
                "如果 wiki_search 没有找到对应内容，说明该文件可能尚未处理，请如实告知用户。"
            )
        messages = [
            {"role": "system", "content": sys_prompt},
            *history,
            {"role": "user", "content": user_input},
        ]

        # 保存用户消息
        if self._conv:
            self._conv.save_turn(session_id, "user", user_input)

        max_turns = 200  # 安全上限，正常情况下 LLM 无工具调用时自然退出
        for turn in range(max_turns):
            # 2. 流式调用 LLM（实时输出 token），429 自动重试
            try:
                stream = self._call_llm_with_retry(messages)
            except Exception as e:
                logger.exception("LLM 调用失败 (turn %d): %s", turn, e)
                yield f"\n[LLM 调用失败: {e}]"
                return

            content_parts = []
            tool_calls_acc = {}  # index -> {id, name, arguments}
            is_tool_mode = False

            try:
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    # 内容 token — 无 tool call 时实时输出
                    if delta.content:
                        content_parts.append(delta.content)
                        if not is_tool_mode:
                            yield delta.content

                    # 工具调用 — 累积；有 tool call 时的 content 是 LLM 思考，不再输出
                    if delta.tool_calls:
                        is_tool_mode = True
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id": tc.id or f"call_{idx}_{int(time.time())}",
                                    "name": "",
                                    "arguments": "",
                                }
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_acc[idx]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_acc[idx]["arguments"] += tc.function.arguments
            except Exception as e:
                logger.exception("流式读取中断 (turn %d): %s", turn, e)
                yield f"\n[流式响应中断: {e}]"
                return

            # 3. 无 tool call → 保存后退出（token 已在上方实时 yield）
            if not is_tool_mode:
                full_text = "".join(content_parts)

                # 学习模式：清理保存的内容（不含 __SUGGESTIONS__）
                if mode == "learn" and full_text:
                    _, clean_text = self._extract_suggestions(full_text)
                    if self._conv:
                        self._conv.save_turn(session_id, "assistant", clean_text)
                elif self._conv:
                    self._conv.save_turn(session_id, "assistant", full_text)
                return

            # 4. 有 tool call → 构造 assistant message 并执行工具
            full_content = "".join(content_parts)
            tool_call_msgs = []
            for idx in sorted(tool_calls_acc.keys()):
                tc = tool_calls_acc[idx]
                tool_call_msgs.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                })

            messages.append({
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": tool_call_msgs,
            })

            # 批量操作提示：多个 document_ingest 时告知用户进度
            ingest_calls = [tc for tc in tool_calls_acc.values()
                           if tc["name"] == "document_ingest"]
            if len(ingest_calls) >= 2:
                file_names = []
                for tc in ingest_calls:
                    try:
                        args = json.loads(tc["arguments"])
                        p = args.get("path", "")
                        file_names.append(os.path.basename(p))
                    except Exception:
                        pass
                if file_names:
                    est_min = max(1, len(file_names) * 60 // 60)
                    yield {
                        "__type__": "tool_status", "status": "running",
                        "name": "document_ingest", "label": f"批量摄入 {len(file_names)} 个文件",
                        "estimate": f"~{est_min} 分钟",
                        "files": file_names[:10],
                    }

            for idx in sorted(tool_calls_acc.keys()):
                tc = tool_calls_acc[idx]
                tool_name = tc["name"]
                meta = TOOL_META.get(tool_name, {})
                label = meta.get("label", tool_name)
                estimate = meta.get("estimate", "")

                # 发送工具开始事件
                yield {
                    "__type__": "tool_status", "status": "running",
                    "name": tool_name, "label": label, "estimate": estimate,
                }

                t0 = time.time()

                tool_obj = self._tools.get(tool_name) if self._tools else None
                # 仅真正覆写了 stream_execute 的工具走流式进度（避免所有 BaseTool 都开线程）
                from src.tools.interfaces import BaseTool
                use_stream = (
                    tool_obj is not None
                    and type(tool_obj).stream_execute is not BaseTool.stream_execute
                )

                if use_stream:
                    result = yield from self._execute_tool_streamed(tc, tool_obj)
                else:
                    result = self._execute_tool_dict(tc)

                elapsed = time.time() - t0
                logger.info("工具 %s 返回 (%.1fs): %s", tool_name, elapsed,
                            _safe_json_dumps(result, ensure_ascii=False)[:200])

                # 发送工具完成事件
                yield {
                    "__type__": "tool_status", "status": "done",
                    "name": tool_name, "label": label,
                    "elapsed": round(elapsed, 1),
                }

                # wiki_batch_tags 特殊输出
                if tool_name == "wiki_batch_tags" and isinstance(result, dict):
                    msg = result.get("result", "")
                    if msg:
                        yield f"\n{msg}\n"
                # 错误回显：只对用户主动触发的操作报错，查询类工具静默
                elif isinstance(result, dict) and result.get("error"):
                    error_msg = result["error"]
                    if tool_name == "document_ingest" and _is_binary_file(tc):
                        logger.info("document_ingest binary file error (silent): %s", error_msg[:120])
                    elif tool_name in ("wiki_read_page", "wiki_update_page",
                                       "wiki_search", "wiki_list_pages",
                                       "wiki_link", "graph_query"):
                        logger.info("查询工具 %s 返回错误（静默）: %s", tool_name, error_msg[:120])
                    else:
                        yield f"\n[tool error] {error_msg}\n"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": _safe_json_dumps(result, ensure_ascii=False),
                })

        # 超过最大轮次
        yield "\n[达到最大工具调用轮次，停止]"

    @staticmethod
    def _extract_suggestions(text: str):
        """从回答中解析 __SUGGESTIONS__ 行，返回 (suggestions_dict|None, clean_text)"""
        import re
        # 匹配各种可能的格式偏差：多余空格、markdown加粗、不同引号等
        match = re.search(
            r'__SUGGESTIONS__\s*:\s*(\[.*\])',
            text, re.DOTALL,
        )
        if not match:
            return None, text
        try:
            raw = match.group(1)
            questions = json.loads(raw)
            if isinstance(questions, list) and len(questions) > 0:
                # 移除整行（从行首到行尾）
                clean = text[:match.start()].rstrip('\n').rstrip()
                return {"__type__": "suggested_questions", "questions": questions}, clean
        except (json.JSONDecodeError, ValueError):
            pass
        return None, text

    def _scan_source_files(self) -> str:
        """扫描 vault 源文件，返回注入 system prompt 的文件列表"""
        if not self._vault_path:
            return ""
        source_exts = ('.pdf', '.pptx', '.ppt', '.doc', '.docx', '.excalidraw')
        files = []
        for root, dirs, filenames in os.walk(self._vault_path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in filenames:
                if f.lower().endswith(source_exts):
                    rel = os.path.relpath(os.path.join(root, f), self._vault_path).replace("\\", "/")
                    files.append(rel)
        if not files:
            return ""
        files.sort()
        listing = "\n".join(f"  - {f}" for f in files)
        return (
            "\n\n## Vault 源文件列表\n"
            "用户提到处理某个文件时，优先从此列表匹配路径，不要猜测：\n"
            f"{listing}"
        )

    def _resolve_converted_files(self, selected_files: list[str]) -> str:
        """检查选中文件的 .flamme/converted/ 产物，返回给 LLM 的提示"""
        if not self._vault_path:
            return ""
        vault = Path(self._vault_path)
        converted = []
        for f in selected_files:
            f_norm = f.replace("\\", "/")
            # 只检查二进制文件
            if not f_norm.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
                continue
            abs_file = vault / f_norm
            if not abs_file.exists():
                continue
            from src.tools.paths import source_dir_for_path, converted_dir
            source_dir = source_dir_for_path(vault, abs_file)
            conv_md = converted_dir(source_dir) / f"{abs_file.stem}.md"
            if conv_md.exists():
                rel_conv = str(conv_md.relative_to(vault)).replace("\\", "/")
                converted.append(f"  - {f_norm} → 已转换为 {rel_conv}")
        if not converted:
            return ""
        return (
            "\n以下文件已有转换产物，无需重新解析：\n"
            + "\n".join(converted) + "\n"
        )

    def _call_llm_with_retry(self, messages: list[dict], max_retries: int = 3):
        """调用 LLM，遇到 429 自动退避重试。返回 stream 对象。"""
        for attempt in range(max_retries + 1):
            try:
                return self._llm.stream_chat_with_tools(
                    messages=messages,
                    tools=ORCHESTRATOR_TOOL_DEFS,
                    tool_choice="auto",
                )
            except Exception as e:
                err_name = type(e).__name__
                if "429" in str(e) or "rate" in str(e).lower() or err_name == "RateLimitError":
                    if attempt < max_retries:
                        wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                        time.sleep(wait)
                        continue
                raise
        raise RuntimeError("LLM 请求失败：超过最大重试次数")

    def _execute_tool_dict(self, tc: dict) -> dict:
        """执行工具 — 接受 dict 格式的 tool call"""
        name = tc["name"]
        try:
            args = json.loads(tc["arguments"])
        except json.JSONDecodeError:
            return {"error": f"参数解析失败: {tc['arguments']}"}

        # 批量标签修复：特殊处理
        if name == "wiki_batch_tags" and self._coordinator:
            return self._handle_batch_tags()

        # 数据库清理
        if name == "wiki_cleanup":
            return self._handle_cleanup(args)

        # 全量同步
        if name == "wiki_sync":
            return self._handle_sync(args)

        # 需要派发给 Worker 的任务
        if name in WORKER_DISPATCH and self._coordinator:
            worker_type = WORKER_DISPATCH[name]
            try:
                task_id = self._coordinator.dispatch(worker_type, args)
                timeout = args.get("timeout_sec") if isinstance(args, dict) else None
                if timeout is None:
                    timeout = 120
                result = self._coordinator.wait_for(task_id, timeout=float(timeout))
                if isinstance(result, dict) and result.get("error"):
                    logger.error(
                        "Worker tool %s failed: task_id=%s status=%s claimed_by=%s error=%s",
                        name,
                        result.get("task_id", task_id),
                        result.get("status"),
                        result.get("claimed_by"),
                        result.get("error"),
                    )
                return result
            except Exception as e:
                logger.exception("Worker 执行异常: tool=%s worker=%s args=%s", name, worker_type, args)
                return {"error": f"Worker 执行失败: {e}"}

        # 本地工具直接执行
        tool = self._tools.get(name)
        if tool:
            try:
                result = tool.execute(args)
                from src.tools.interfaces import ToolResult
                if isinstance(result, ToolResult):
                    if result.is_error:
                        return {"error": result.error}
                    data = result.data
                    # 学习模式文件过滤：对 wiki_search 结果按选中文件过滤
                    if name == "wiki_search" and self._selected_files and isinstance(data, dict):
                        entries = data.get("results", [])
                        filtered = [e for e in entries if e.get("path", "") in self._selected_files]
                        # 如果过滤后为空，保留原始结果（避免完全无结果）
                        if filtered:
                            data = {**data, "results": filtered, "total": len(filtered), "filtered": True}
                    return data if isinstance(data, dict) else {"result": data}
                return result
            except Exception as e:
                logger.exception("工具执行异常: tool=%s args=%s", name, args)
                return {"error": f"工具执行失败: {e}"}

        return {"error": f"未知工具: {name}"}

    def _handle_batch_tags(self) -> dict:
        """扫描缺 tags 的源文档，批量派发给 BatchTagWorker"""
        from src.tools.sync import is_source_doc

        db = self._coordinator._db
        docs = db.list_documents()
        payloads = []
        for doc in docs:
            p = doc["path"]
            if not is_source_doc(p):
                continue
            # 二进制文件无法写入 frontmatter，跳过
            if p.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
                continue
            full_doc = db.get_document(p)
            tags = full_doc.get("tags", []) if full_doc else []
            if not tags:
                # BatchTagWorker 需要绝对路径来读文件
                abs_path = os.path.join(db._vault_path, p) if db._vault_path else p
                payloads.append({"path": abs_path})

        if not payloads:
            return {"result": "所有文档都已有标签，无需修复", "total": 0, "fixed": 0}

        task_ids = self._coordinator.dispatch_batch("batch_tag", payloads)
        results = self._coordinator.wait_for_batch(task_ids, timeout=600)

        done = sum(1 for r in results if not isinstance(r, dict) or "error" not in r)
        failed = len(results) - done
        return {
            "result": f"批量标签修复完成: {done} 成功, {failed} 失败, 共 {len(results)} 个文档",
            "total": len(results),
            "fixed": done,
            "failed": failed,
        }

    def _handle_cleanup(self, args: dict) -> dict:
        """处理知识库清理操作"""
        action = args.get("action", "status")
        db = self._coordinator._db

        if action == "purge_missing":
            deleted = db.purge_missing()
            if not deleted:
                return {"result": "没有文件缺失的记录", "deleted": 0}
            return {
                "result": f"已清理 {len(deleted)} 条文件缺失的 DB 记录",
                "deleted": len(deleted),
                "paths": deleted[:20],
            }

        if action == "purge_graph_noise":
            import re as _re
            vault = self._vault_path or ""
            if not vault:
                return {"error": "vault_path 未配置"}

            # 通过 GraphStore 查询所有单字符噪声节点
            from src.db.graph_store import GraphStore
            gs = GraphStore(db._conn)
            stats = gs.get_stats()
            noise_ids = set()
            for ent in db._conn.execute("SELECT name FROM entities WHERE length(name) = 1").fetchall():
                name = ent[0]
                if _re.match(r'[\u4e00-\u9fff\w]', name):
                    noise_ids.add(name)

            if not noise_ids:
                return {"result": "没有发现噪声节点", "deleted": 0}

            # 删除噪声节点及其关联边
            for nid in noise_ids:
                db._conn.execute("DELETE FROM relations WHERE source = ? OR target = ?", (nid, nid))
                db._conn.execute("DELETE FROM entities WHERE name = ?", (nid,))
            db._conn.commit()

            return {
                "result": f"已从图谱中删除 {len(noise_ids)} 个噪声节点: {sorted(noise_ids)}",
                "deleted": len(noise_ids),
                "noise_ids": sorted(noise_ids),
            }

        if action == "status":
            docs = db.list_documents()
            vault = db._vault_path
            missing = sum(1 for d in docs if vault and not os.path.isfile(os.path.join(vault, d["path"])))
            return {
                "total_docs": len(docs),
                "missing_files": missing,
                "result": f"知识库共 {len(docs)} 条记录, {missing} 条文件缺失",
            }

        return {"error": f"未知操作: {action}"}

    def _handle_sync(self, args: dict) -> dict:
        """全量同步 vault 文件到知识库索引"""
        from src.tools.sync import run_vault_sync, format_sync_summary

        data = run_vault_sync(
            self._coordinator._db,
            self._vault_path,
            self._tools,
            embed=args.get("embed", True),
            graph=args.get("graph", False),
        )
        if data.get("error"):
            return data
        data["result"] = format_sync_summary(data)
        return data

    def _execute_tool_streamed(self, tc: dict, tool) -> dict:
        """用线程运行工具的 stream_execute，实时 yield 进度到生成器。

        工具的 stream_execute() 是生成器：yield str 进度消息，最终 return ToolResult。
        这里在线程中驱动生成器，通过 queue 把进度传回主线程。
        注意：此方法 yield 进度字符串，return 最终 dict 结果。
        但由于它被 chat() 生成器调用（for 循环中），我们用 yield from 模式。
        """
        try:
            args = json.loads(tc["arguments"])
        except json.JSONDecodeError:
            return {"error": f"参数解析失败: {tc['arguments']}"}

        progress_q = queue_mod.Queue()
        final_result = {"error": "stream_execute 未返回结果"}

        # 在 _execute_tool_streamed 作用域 import，确保闭包 _run 能访问
        from src.tools.interfaces import ToolResult as _ToolResult

        def _run():
            nonlocal final_result
            try:
                gen = tool.stream_execute(args)
                while True:
                    try:
                        item = next(gen)
                    except StopIteration as si:
                        if si.value is not None:
                            final_result = si.value
                        break
                    if isinstance(item, str):
                        progress_q.put(item)
                    elif isinstance(item, _ToolResult):
                        final_result = item
            except Exception as e:
                logger.exception("stream_execute 异常: %s", e)
                final_result = _ToolResult.err(f"执行异常: {e}")
                progress_q.put(f"执行异常: {e}")
            finally:
                progress_q.put(None)  # sentinel

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        # 实时输出进度
        while True:
            try:
                msg = progress_q.get(timeout=5)
            except queue_mod.Empty:
                continue
            if msg is None:
                break
            yield {
                "__type__": "tool_status", "status": "progress",
                "name": tc["name"], "label": TOOL_META.get(tc["name"], {}).get("label", tc["name"]),
                "message": msg,
            }

        thread.join(timeout=10)

        # 转换 ToolResult -> dict
        if isinstance(final_result, _ToolResult):
            if final_result.is_error:
                return {"error": final_result.error}
            return final_result.data if isinstance(final_result.data, dict) else {"result": final_result.data}
        return final_result
