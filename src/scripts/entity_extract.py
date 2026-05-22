"""
LLM 实体提取 — 从笔记内容提取实体 JSON，供 wiki_entity.py generate 使用

用法:
  python scripts/entity_extract.py <file_or_dir> [--output entities.json] [--dry-run] [--interval 2.0]

示例:
  python scripts/entity_extract.py "pro/人工智能导论/2.无信息搜索.md"
  python scripts/entity_extract.py "pro/人工智能导论" --output entities.json
  python scripts/entity_extract.py "lite/微积分②" --dry-run
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from src.scripts import VAULT, all_entity_files, all_flamme_dirs
MAX_CONTENT_CHARS = 12000

SYSTEM_PROMPT = """你是知识管理助手。从给定笔记中提取核心实体（概念、算法、定理、框架、人物、模型）。

规则：
1. 输出严格 JSON，不包含 markdown 标记
2. 格式: {"entities": [{...}]}
3. 每个 entity 包含: title, summary, key_points, related, source, tags
4. title 必须简洁明确（2-8字优先），不可与已有实体重复
5. summary: 一段话概括核心内容
6. key_points: 3-7个要点，格式"要点名: 简要说明"
7. related: 列出相关的概念名（不含方括号）
8. source: 来源笔记标题
9. tags: 3-5个标签
10. 只提取值得拥有独立页面的核心实体。判断标准：该概念是否有足够复杂度，需要 3 个以上要点才能解释清楚？如果一句话就能说清楚，不要提取
11. 优先补充已有实体页的内容（在 related 中引用），而非创建新实体。一篇笔记产生 0-2 个新实体是正常的
12. 以下内容不是实体：格式规则、写作方法、排序方式、通用编程原则、常识性概念"""


# ── 实体名收集 ────────────────────────────────────────────────────────

def get_existing_entity_names():
    """扫描 vault/entities/ 获取已有实体标题"""
    return all_entity_files()


# ── 内容处理 ──────────────────────────────────────────────────────────

def extract_level(filepath):
    """从文件路径推断级别"""
    for p in filepath.parts:
        if p in ("pro", "lite", "raw"):
            return p
    return "lite"


def truncate_content(text, max_chars=MAX_CONTENT_CHARS):
    """截断过长内容"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[Content truncated for API limits]"


# ── Prompt 构建 ───────────────────────────────────────────────────────

def build_messages(title, content, existing_entities, level):
    """构建 API 调用的 messages"""
    entity_list = ", ".join(sorted(existing_entities)) if existing_entities else "无"
    user_msg = f"""## 笔记信息
- 标题: {title}
- 级别: {level}

## 已有实体（不要重复提取）
{entity_list}

## 笔记内容
{content}"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg}
    ]


# ── 响应解析 ──────────────────────────────────────────────────────────

def parse_entity_json(raw):
    """解析 LLM 响应为 entity dict，兼容 markdown 代码块包裹"""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                print(f"  [parse error] regex fallback returned non-JSON")
                return None
        else:
            print(f"  [parse error] no JSON found in response")
            return None

    if "entities" not in data:
        print(f"  [parse error] missing 'entities' key")
        return None

    # 规范化：related 字段确保为列表
    for ent in data["entities"]:
        if "related" in ent and isinstance(ent["related"], str):
            ent["related"] = [r.strip() for r in ent["related"].split() if r.strip()]

    return data


def is_trivial_entity(ent, existing_names):
    """检查实体是否过于琐碎"""
    title = ent.get("title", "")
    summary = ent.get("summary", "")
    kp = ent.get("key_points", [])

    # summary 短于 30 字 = 没有实质内容
    if len(summary) < 30:
        return True
    # 少于 3 个要点 = 不够复杂
    if len(kp) < 3:
        return True
    # 标题包含"规则""方法""原则""策略"等词且不涉及具体领域 = 通用方法
    trivial_words = ["规则", "方法", "原则", "策略", "格式", "要求", "步骤"]
    if any(w in title for w in trivial_words) and not any(
        w in title for w in ["搜索", "算法", "模型", "网络", "函数", "逻辑", "电路", "矩阵"]
    ):
        return True
    return False


# ── 单文件处理 ────────────────────────────────────────────────────────

def extract_from_file(filepath, existing_entities, client=None,
                      dry_run=False, interval=2.0):
    """处理单个笔记文件，返回 entity dict 或 None"""
    from llm_utils import get_client, call_llm, strip_frontmatter, extract_title

    filepath = Path(filepath)
    if not filepath.exists():
        print(f"  [skip] not found: {filepath}")
        return None

    text = filepath.read_text(encoding="utf-8")
    title = extract_title(text) or filepath.stem
    level = extract_level(filepath)
    content = truncate_content(strip_frontmatter(text))

    if level == "raw":
        print(f"  [skip] raw level, no extraction: {filepath.name}")
        return None

    messages = build_messages(title, content, existing_entities, level)

    if dry_run:
        print(f"  [dry-run] {filepath.name} (level={level}, {len(content)} chars)")
        print(f"    prompt tokens ≈ {len(content) // 3}")
        return {"entities": [], "_dry_run": True, "_source": str(filepath)}

    if client is None:
        client = get_client()

    print(f"  [extract] {filepath.name} (level={level}) ...")
    raw = call_llm(client, messages)
    result = parse_entity_json(raw)

    if result:
        n = len(result.get("entities", []))
        print(f"  [done] {n} entities extracted")
    else:
        print(f"  [warn] failed to parse response")

    return result


# ── 目录处理 ──────────────────────────────────────────────────────────

def extract_from_directory(dirpath, existing_entities, client=None,
                           dry_run=False, interval=2.0):
    """处理目录下所有 .md 文件（优先扫描 .flamme/converted/）"""
    from flamme_paths import converted_dir
    dirpath = Path(dirpath)
    # 优先在 .flamme/converted/ 下查找
    cand = converted_dir(dirpath)
    scan_dir = cand if any(cand.glob("*.md")) else dirpath
    files = sorted(
        f for f in scan_dir.rglob("*.md")
        if not f.name.endswith(".excalidraw.md") and not f.name.startswith("~$")
    )

    if not files:
        print(f"No .md files found in {dirpath}")
        return []

    print(f"Found {len(files)} file(s) in {dirpath}\n")

    all_entities = []
    for i, f in enumerate(files):
        result = extract_from_file(f, existing_entities, client, dry_run, interval)
        if result and "entities" in result:
            all_entities.extend(result["entities"])
            for ent in result["entities"]:
                existing_entities.add(ent.get("title", ""))

        if not dry_run and i < len(files) - 1:
            time.sleep(interval)

        print()

    return all_entities


# ── Main ──────────────────────────────────────────────────────────────

def main():
    from llm_utils import get_client

    parser = argparse.ArgumentParser(description="LLM 实体提取")
    parser.add_argument("path", help="文件或目录路径")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只显示 prompt 不调 API")
    parser.add_argument("--interval", type=float, default=2.0, help="API 调用间隔秒数")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    existing = get_existing_entity_names()
    print(f"已有 {len(existing)} 个实体页\n")

    client = None if args.dry_run else get_client()

    if path.is_dir():
        entities = extract_from_directory(path, existing, client, args.dry_run, args.interval)
    else:
        result = extract_from_file(path, existing, client, args.dry_run, args.interval)
        entities = result.get("entities", []) if result else []

    if not entities:
        print("No entities extracted.")
        return

    filtered = []
    for e in entities:
        if not isinstance(e, dict) or not e.get("title"):
            continue
        if is_trivial_entity(e, existing):
            print(f"  [filter] {e['title']}: trivial entity, skipped")
            continue
        filtered.append(e)

    output = {"entities": filtered}

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWritten {len(output['entities'])} entities to {args.output}")
    else:
        print(f"\n{len(output['entities'])} entities:")
        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
