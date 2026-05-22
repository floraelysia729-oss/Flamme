"""
LLM Wiki 模板化 Entity 生成器

用法:
  # 从 JSON 文件生成 entity 页
  python scripts/wiki_entity.py generate entities.json

  # 从 JSON 字符串生成
  python scripts/wiki_entity.py generate '{"entities": [...]}'

  # 生成 JSON 模板（供 LLM 填写）
  python scripts/wiki_entity.py template "人工智能导论" --source "1.绪论,2.搜索"

JSON 输入格式（LLM 一次调用输出）:
{
  "entities": [
    {
      "title": "无信息搜索",
      "summary": "不利用目标信息的搜索策略...",
      "key_points": ["BFS: FIFO, 完备最优 O(b^d)", "DFS: LIFO, 不完备 O(bm)", ...],
      "related": ["有信息搜索", "递归与栈"],
      "source": "2.无信息搜索",
      "tags": ["搜索", "BFS", "DFS"]
    },
    ...
  ]
}
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from src.scripts import VAULT, entities_dir

ENTITY_TEMPLATE = """---
title: "{title}"
type: entity
created: {today}
updated: {today}
sources:
  - "[[{source}]]"
tags: [{tags}]
related:
{related}
---

# {title}

{summary}

## 要点

{key_points}

## 关联概念

{related_links}

## 来源

- [[{source}]]
"""


def generate_entities(data: dict):
    """从 JSON 数据生成 entity 页，写入 vault/entities/"""
    entities = data.get("entities", [])
    if not entities:
        print("No entities found in input.")
        return

    created = 0
    skipped = 0
    for ent in entities:
        title = ent.get("title", "").strip()
        if not title:
            print(f"  [skip] missing title")
            skipped += 1
            continue

        out_path = entities_dir(VAULT) / f"{title}.md"

        # 检查是否已存在
        if out_path.exists():
            print(f"  [skip] {title} already exists")
            skipped += 1
            continue

        today = date.today().isoformat()
        source = ent.get("source", "")
        tags = ", ".join(ent.get("tags", []))
        related_list = ent.get("related", [])
        related_fm = "\n".join(f'  - "[[{r}]]"' for r in related_list) if related_list else "  []"
        summary = ent.get("summary", "")
        key_points = ent.get("key_points", [])

        # 质量门槛：key_points 少于 3 条或 summary 短于 30 字的跳过
        if len(key_points) < 3 or len(summary) < 30:
            print(f"  [skip] {title}: too trivial ({len(key_points)} points, {len(summary)} chars)")
            skipped += 1
            continue

        kp_md = "\n".join(f"- {p}" for p in key_points) if key_points else ""
        related_links = " ".join(f"[[{r}]]" for r in related_list) if related_list else ""

        content = ENTITY_TEMPLATE.format(
            title=title, today=today, source=source, tags=tags,
            related=related_fm, summary=summary,
            key_points=kp_md, related_links=related_links
        )

        out_path.write_text(content, encoding="utf-8")
        print(f"  [created] {title}")
        created += 1

    print(f"\nDone. {created} created, {skipped} skipped.")


def print_template(topic_name: str, sources: str):
    """输出 JSON 模板供 LLM 填写"""
    source_list = [s.strip() for s in sources.split(",")]
    template = {
        "entities": [
            {
                "title": f"概念名称{i+1}",
                "summary": "一段话概括这个概念的核心内容和关键信息",
                "key_points": ["要点1: 说明", "要点2: 说明", "要点3: 说明"],
                "related": ["相关概念1", "相关概念2"],
                "source": source_list[0] if source_list else "",
                "tags": ["标签1", "标签2"]
            }
            for i in range(3)
        ]
    }
    print(json.dumps(template, ensure_ascii=False, indent=2))
    print(f"\n# 主题: {topic_name}")
    print(f"# 来源: {sources}")
    print(f"# 请根据以上来源内容填写 {len(source_list)}-7 个 entity")


def main():
    parser = argparse.ArgumentParser(description="模板化 Entity 生成器")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="从 JSON 生成 entity 页")
    gen.add_argument("input", help="JSON 文件路径或 JSON 字符串")
    gen.add_argument("--source-dir", help="目标源文件夹（vault 相对路径，如 pro/矩阵论）")

    tpl = sub.add_parser("template", help="输出 JSON 模板")
    tpl.add_argument("topic", help="主题名称")
    tpl.add_argument("--source", required=True, help="来源文件列表，逗号分隔")

    args = parser.parse_args()

    if args.command == "generate":
        # 尝试读取文件，否则当作 JSON 字符串
        input_path = Path(args.input)
        if input_path.exists():
            data = json.loads(input_path.read_text(encoding="utf-8"))
        else:
            data = json.loads(args.input)
        generate_entities(data)

    elif args.command == "template":
        print_template(args.topic, args.source)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
