"""
LLM 标签补全 — 扫描缺标签笔记，调 LLM 补充 tags 字段

用法:
  python scripts/tag_notes.py <file_or_dir> [--dry-run] [--interval 2.0] [--min-tags 3] [--force]

示例:
  python scripts/tag_notes.py "pro/人工智能导论" --dry-run
  python scripts/tag_notes.py "lite/微积分②"
  python scripts/tag_notes.py "pro/高程/2026-03-02.md" --force
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from src.scripts import VAULT


# ── 标签词频收集 ──────────────────────────────────────────────────────

def get_tag_vocabulary():
    """扫描 vault 源 .md 的 tags，返回 {tag: count}"""
    from llm_utils import read_frontmatter
    from src.tools.sync import is_source_doc

    tags = {}
    for md_file in VAULT.rglob("*.md"):
        if md_file.name.endswith(".excalidraw.md"):
            continue
        rel = str(md_file.relative_to(VAULT)).replace("\\", "/")
        if not is_source_doc(rel):
            continue
        text = md_file.read_text(encoding="utf-8")
        fm = read_frontmatter(text)
        if fm and "tags" in fm:
            for tag in fm["tags"]:
                if isinstance(tag, str):
                    tags[tag] = tags.get(tag, 0) + 1
    return tags


# ── 需要标签检测 ──────────────────────────────────────────────────────

def needs_tagging(filepath, min_tags=3, force=False):
    """判断文件是否需要打标签"""
    from llm_utils import read_frontmatter

    if force:
        return True
    text = filepath.read_text(encoding="utf-8")
    fm = read_frontmatter(text)
    if not fm:
        return True
    tags = fm.get("tags", [])
    if not tags or tags == []:
        return True
    if isinstance(tags, list) and len(tags) < min_tags:
        return True
    return False


# ── Prompt 构建 ───────────────────────────────────────────────────────

def build_tagging_messages(title, content, tag_vocabulary):
    """构建标签建议的 API messages"""
    top_tags = sorted(tag_vocabulary.items(), key=lambda x: -x[1])[:50]
    vocab_str = ", ".join(f"{t}({c})" for t, c in top_tags)

    system = """你是知识管理助手。为给定笔记建议合适的标签。

规则：
1. 输出严格 JSON 数组，如 ["标签1", "标签2", "标签3"]
2. 提供 3-7 个标签
3. 优先使用已有标签（保持一致性）
4. 标签应该简洁（1-4字为主）
5. 不要包含笔记标题本身"""

    user = f"""## 已有标签词频（优先复用）
{vocab_str}

## 笔记标题
{title}

## 笔记内容
{content}"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ]


# ── 响应解析 ──────────────────────────────────────────────────────────

def parse_tag_response(raw):
    """解析 LLM 响应为标签列表"""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return [str(t) for t in result]
    except json.JSONDecodeError:
        pass

    m = re.search(r"\[.*?\]", text, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group())
            return [str(t) for t in result]
        except json.JSONDecodeError:
            pass

    if "," in text:
        return [t.strip().strip('"').strip("'") for t in text.split(",") if t.strip()]

    return []


# ── Frontmatter 更新 ──────────────────────────────────────────────────

def update_tags_in_frontmatter(text, new_tags):
    """更新 frontmatter 中的 tags 字段，兼容 inline 和多行格式"""
    from llm_utils import read_frontmatter

    tags_str = ", ".join(new_tags)
    replacement = f"tags: [{tags_str}]"

    # 1. 匹配 inline 格式: tags: [tag1, tag2]
    new_text, n = re.subn(r"^tags:\s*\[.*?\]", replacement, text, flags=re.MULTILINE, count=1)
    if n > 0:
        return new_text

    # 2. 匹配多行格式:
    #    tags:
    #      - tag1
    #      - tag2
    new_text, n = re.subn(r"^tags:\s*\n(?:\s+-\s+.*\n?)+", replacement, text, flags=re.MULTILINE, count=1)
    if n > 0:
        return new_text

    # 3. fallback: 在 frontmatter 末尾添加 tags 字段
    def add_tags(m):
        return m.group(0) + f"\ntags: [{tags_str}]"

    new_text = re.sub(r"^(---\n(?:.*\n)*?)---", add_tags, text, count=1)

    # 校验
    fm_after = read_frontmatter(new_text)
    if fm_after and set(fm_after.get("tags", [])) != set(new_tags):
        print(f"  [warn] tag update may have failed, frontmatter changed unexpectedly")

    return new_text


# ── 单文件处理 ────────────────────────────────────────────────────────

def tag_file(filepath, tag_vocabulary, client=None, dry_run=False,
             min_tags=3, force=False):
    """处理单个文件。
    返回 list = 成功, None = 已有标签跳过, False = 失败"""
    from llm_utils import get_client, call_llm, strip_frontmatter, extract_title

    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8")

    if not needs_tagging(filepath, min_tags, force):
        print(f"  [skip] already tagged: {filepath.name}")
        return None

    title = extract_title(text) or filepath.stem
    content = strip_frontmatter(text)[:4000]

    messages = build_tagging_messages(title, content, tag_vocabulary)

    if dry_run:
        print(f"  [dry-run] {filepath.name} ({len(content)} chars)")
        return []

    if client is None:
        client = get_client()

    print(f"  [tag] {filepath.name} ...")
    raw = call_llm(client, messages, max_tokens=1024)
    tags = parse_tag_response(raw)

    if not tags:
        print(f"  [warn] no tags parsed")
        return False

    new_text = update_tags_in_frontmatter(text, tags)
    filepath.write_text(new_text, encoding="utf-8")
    print(f"  [done] tags: {tags}")
    return tags


# ── Main ──────────────────────────────────────────────────────────────

def main():
    from llm_utils import get_client

    parser = argparse.ArgumentParser(description="LLM 标签补全")
    parser.add_argument("path", help="文件或目录路径")
    parser.add_argument("--dry-run", action="store_true", help="只显示不执行")
    parser.add_argument("--interval", type=float, default=2.0, help="API 调用间隔秒数")
    parser.add_argument("--min-tags", type=int, default=3, help="少于此数量的文件才处理")
    parser.add_argument("--force", action="store_true", help="强制重新打标签")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    tag_vocab = get_tag_vocabulary()
    print(f"已有 {len(tag_vocab)} 种标签\n")

    client = None if args.dry_run else get_client()

    if path.is_dir():
        files = sorted(
            f for f in path.rglob("*.md")
            if not f.name.endswith(".excalidraw.md") and not f.name.startswith("~$")
        )
        if not files:
            print(f"No .md files found in {path}")
            return

        print(f"Found {len(files)} file(s) in {path}\n")

        tagged = 0
        for i, f in enumerate(files):
            result = tag_file(f, tag_vocab, client, args.dry_run,
                             args.min_tags, args.force)
            if result is not None:
                tagged += 1
            if not args.dry_run and i < len(files) - 1:
                time.sleep(args.interval)

        print(f"\nDone. {tagged} file(s) tagged.")

    else:
        result = tag_file(path, tag_vocab, client, args.dry_run,
                         args.min_tags, args.force)
        if result:
            print(f"\nDone. Tags: {result}")
        elif args.dry_run:
            print("\nDry run complete.")


if __name__ == "__main__":
    main()
