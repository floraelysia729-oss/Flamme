"""
LLM Wiki 维护脚本 — 机械操作自动化

用法:
  python scripts/wiki_fix.py --fix-related     # 统一 related 为 [[wikilink]] 格式
  python scripts/wiki_fix.py --rebuild-index   # 从 wiki/ 目录重建 index.md
  python scripts/wiki_fix.py --log "操作描述"   # 追加 log.md 操作记录
  python scripts/wiki_fix.py --lint            # 检测孤立页面和缺失引用
  python scripts/wiki_fix.py --check-fm        # 检查 frontmatter 完整性
  python scripts/wiki_fix.py --archive-log     # 归档半年前的日志条目
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from src.scripts import VAULT, all_flamme_dirs, all_wiki_page_files, entities_dir, topics_dir

INDEX = VAULT / "index.md"
LOG = VAULT / "log.md"
LOG_ARCHIVE = VAULT / "log-archive"


def _all_wiki_files() -> list[Path]:
    """扫描 vault 根 wiki 页 + 遗留 .flamme/ 下的 .md"""
    files = list(all_wiki_page_files(VAULT))
    seen = {f.resolve() for f in files}
    for fd in all_flamme_dirs(VAULT):
        for md in fd.rglob("*.md"):
            if md.resolve() not in seen:
                files.append(md)
                seen.add(md.resolve())
    return sorted(files)
ARCHIVE_THRESHOLD_LINES = 500
ARCHIVE_THRESHOLD_MONTHS = 6

ENTITY_TEMPLATE = """---
title: "{title}"
type: entity
created: {date}
updated: {date}
sources:{sources}
tags: [{tags}]
related:{related}
---

# {title}

{summary}

## 关联概念

{related_section}

## 来源

{sources_section}
"""


# ── Frontmatter 工具 ────────────────────────────────────────────────

def read_frontmatter(text: str) -> dict | None:
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
                # inline list
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


def is_wikilink(s: str) -> bool:
    """检查字符串是否已经是 [[wikilink]] 格式"""
    return s.startswith("[[") and s.endswith("]]")


def normalize_wikilink(s: str) -> str:
    """统一为 [[wikilink]] 格式"""
    s = s.strip().strip('"').strip("'")
    if s.startswith("[[") and s.endswith("]]"):
        return s
    # 裸路径如 entities/范数 → 范数
    name = Path(s).stem if "/" in s else s
    return f"[[{name}]]"


# ── --fix-related ──────────────────────────────────────────────────

def fix_related():
    """扫描所有 .flamme/ 下 .md，将 related 字段统一为 [[wikilink]]"""
    fixed = 0
    for md_file in _all_wiki_files():
        text = md_file.read_text(encoding="utf-8")
        # 匹配 related 字段及其列表项
        def replace_related(m):
            nonlocal fixed
            block = m.group(0)
            lines = block.split("\n")
            changed = False
            new_lines = []
            for line in lines:
                if line.startswith("  - "):
                    val = line[4:].strip().strip('"').strip("'")
                    wl = normalize_wikilink(val)
                    if wl != val:
                        changed = True
                        fixed += 1
                    new_lines.append(f'  - "{wl}"')
                else:
                    new_lines.append(line)
            return "\n".join(new_lines) if changed else block

        new_text = re.sub(
            r"related:\n(?:  - .+\n)*",
            replace_related,
            text
        )
        if new_text != text:
            md_file.write_text(new_text, encoding="utf-8")
            print(f"  fixed: {md_file.relative_to(VAULT)}")
    print(f"\nDone. {fixed} related entries fixed.")


# ── --rebuild-index ────────────────────────────────────────────────

def get_first_heading(text: str) -> str:
    """提取第一个 # 标题"""
    m = re.search(r"^# (.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def get_entity_summary(text: str) -> str:
    """从 entity 正文提取一行摘要（跳过标题、表格、引用）"""
    body = re.sub(r"^---\n.*?\n---\n*", "", text, flags=re.DOTALL)
    body = re.sub(r"^#+ .+\n*", "", body)  # 跳过标题
    for line in body.strip().split("\n"):
        line = line.strip()
        # 跳过空行、标题、表格分隔、引用、代码块
        if (line
            and not line.startswith("#")
            and not line.startswith("|")
            and not line.startswith(">")
            and not line.startswith("```")
            and not line.startswith("---")
            and len(line) > 5):
            return line[:60] + ("..." if len(line) > 60 else "")
    return ""


def rebuild_index():
    """检查 index.md 是否覆盖所有 wiki 页面，报告缺漏"""
    index_text = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""

    # 收集所有 .flamme/ 下的页面
    all_wiki_pages = set()
    for md_file in _all_wiki_files():
        all_wiki_pages.add(md_file.stem)

    # 收集 index.md 中已有的链接
    indexed = set()
    for link in re.findall(r"\[\[([^\]]+)\]\]", index_text):
        name = Path(link).stem if "/" in link else link
        indexed.add(name)

    # 找缺漏
    missing_in_index = all_wiki_pages - indexed
    if missing_in_index:
        print(f"index.md 缺漏 {len(missing_in_index)} 个页面：")
        for name in sorted(missing_in_index):
            kind = "?"
            if (entities_dir(VAULT) / f"{name}.md").exists():
                kind = "entity"
            elif (topics_dir(VAULT) / f"{name}.md").exists():
                kind = "topic"
            else:
                for fd in all_flamme_dirs(VAULT):
                    if (fd / "topics" / f"{name}.md").exists():
                        kind = "topic"
                        break
                    if (fd / "entities" / f"{name}.md").exists():
                        kind = "entity"
                        break
                    if (fd / "explorations" / f"{name}.md").exists():
                        kind = "exploration"
                        break
            print(f"  - {name} ({kind})")
    else:
        print("index.md 已覆盖所有 wiki 页面。")

    # 找 index 中引用但不存在的
    phantom = indexed - all_wiki_pages
    if phantom:
        print(f"\nindex.md 引用了 {len(phantom)} 个不存在的页面：")
        for name in sorted(phantom):
            print(f"  - {name}")


# ── --log ──────────────────────────────────────────────────────────

def append_log(message: str):
    """追加操作记录到 log.md"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## [{now}] {message}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"Appended to log.md: [{now}] {message}")


# ── --lint ─────────────────────────────────────────────────────────

def lint():
    """检测孤立页面和缺失引用"""
    # 1. 建立引用图：每个页面引用了谁
    all_pages = set()
    ref_count = {}  # page_name -> 被引用次数
    refs_from = {}  # page_name -> [引用者列表]

    # 构建快速查找：vault 根 wiki 页 + 遗留 .flamme/ 路径
    _entity_names = set()
    _topic_names = set()
    ent_dir = entities_dir(VAULT)
    top_dir = topics_dir(VAULT)
    if ent_dir.exists():
        _entity_names.update(f.stem for f in ent_dir.glob("*.md"))
    if top_dir.exists():
        _topic_names.update(f.stem for f in top_dir.glob("*.md"))
    for fd in all_flamme_dirs(VAULT):
        ed = fd / "entities"
        td = fd / "topics"
        if ed.exists():
            _entity_names.update(f.stem for f in ed.glob("*.md"))
        if td.exists():
            _topic_names.update(f.stem for f in td.glob("*.md"))

    for md_file in _all_wiki_files():
        stem = md_file.stem
        all_pages.add(stem)
        ref_count.setdefault(stem, 0)
        refs_from.setdefault(stem, [])

        text = md_file.read_text(encoding="utf-8")
        # 提取所有 [[wikilink]]
        links = re.findall(r"\[\[([^\]]+)\]\]", text)
        for link in links:
            name = Path(link).stem if "/" in link else link
            if name in all_pages or name in _entity_names or name in _topic_names:
                ref_count[name] = ref_count.get(name, 0) + 1
                refs_from.setdefault(name, []).append(stem)

    # 2. 找孤立页面（没有被任何其他页面引用）
    orphaned = []
    for name in sorted(all_pages):
        if ref_count.get(name, 0) == 0:
            orphaned.append(name)

    if orphaned:
        print(f"孤立页面（无入站引用）: {len(orphaned)}")
        for name in orphaned:
            print(f"  - {name}")
    else:
        print("无孤立页面。")

    # 3. 找缺失概念页（被引用但不存在的）
    missing = []
    for name in sorted(ref_count.keys()):
        if name not in all_pages:
            missing.append(name)

    if missing:
        print(f"\n缺失页面（被引用但不存在）: {len(missing)}")
        for name in missing:
            print(f"  - {name} (被 {refs_from.get(name, [])} 引用)")
    else:
        print("无缺失页面。")

    # 4. 检查 frontmatter 完整性
    fm_issues = []
    for md_file in _all_wiki_files():
        text = md_file.read_text(encoding="utf-8")
        fm = read_frontmatter(text)
        if not fm:
            fm_issues.append(f"{md_file.relative_to(VAULT)}: 缺少 frontmatter")
            continue
        # 检查路径中是否包含 entities/ 或 topics/ 子目录
        rel_str = str(md_file.relative_to(VAULT))
        if "/entities/" in rel_str.replace("\\", "/") and "type" not in fm:
            fm_issues.append(f"{md_file.relative_to(VAULT)}: entity 缺少 type 字段")
        if "/topics/" in rel_str.replace("\\", "/") and "type" not in fm:
            fm_issues.append(f"{md_file.relative_to(VAULT)}: topic 缺少 type 字段")

    if fm_issues:
        print(f"\nFrontmatter 问题: {len(fm_issues)}")
        for issue in fm_issues:
            print(f"  - {issue}")


# ── --check-fm ─────────────────────────────────────────────────────

def check_frontmatter():
    """检查 vault 源 .md 的 frontmatter 完整性"""
    from src.tools.sync import is_source_doc

    issues = []
    for md_file in sorted(VAULT.rglob("*.md")):
        if md_file.name.endswith(".excalidraw.md"):
            continue
        rel = str(md_file.relative_to(VAULT)).replace("\\", "/")
        if not is_source_doc(rel):
            continue
        text = md_file.read_text(encoding="utf-8")
        fm = read_frontmatter(text)
        if not fm:
            issues.append(f"MISSING: {md_file.relative_to(VAULT)}")
            continue
        required = ["title", "date", "source", "level", "tags", "status"]
        missing_fields = [f for f in required if f not in fm or not fm[f]]
        if missing_fields:
            issues.append(f"INCOMPLETE: {md_file.relative_to(VAULT)} missing {missing_fields}")

    if issues:
        print(f"Found {len(issues)} issues:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("All files have complete frontmatter.")


# ── --archive-log ──────────────────────────────────────────────────

def archive_log():
    """log.md 超 500 行时，把半年前的条目移到 log-archive/YYYY-MM.md"""
    if not LOG.exists():
        print("log.md not found")
        return

    lines = LOG.read_text(encoding="utf-8").splitlines(keepends=True)
    total = len(lines)

    if total <= ARCHIVE_THRESHOLD_LINES:
        print(f"log.md has {total} lines (threshold {ARCHIVE_THRESHOLD_LINES}), no archiving needed")
        return

    # 解析每个条目的起始位置和日期
    # 格式: ## [YYYY-MM-DD HH:mm] ...
    entry_pattern = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})")
    entries = []  # [(start_line, date_str, end_line)]
    for i, line in enumerate(lines):
        m = entry_pattern.match(line)
        if m:
            entries.append((i, m.group(1)))

    if not entries:
        print("No dated entries found")
        return

    # 计算截止日期（6个月前）
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    cutoff = (datetime.now() - relativedelta(months=ARCHIVE_THRESHOLD_MONTHS)).strftime("%Y-%m-%d")

    # 分组：要归档的 vs 保留的
    archive_indices = [i for i, (_, d) in enumerate(entries) if d < cutoff]

    if not archive_indices:
        print(f"No entries older than {cutoff}")
        return

    # 按月份分组归档
    LOG_ARCHIVE.mkdir(exist_ok=True)
    by_month = {}  # {YYYY-MM: [entry_lines]}
    for idx in archive_indices:
        start = entries[idx][0]
        end = entries[idx + 1][0] if idx + 1 < len(entries) else len(lines)
        date_str = entries[idx][1][:7]  # YYYY-MM
        by_month.setdefault(date_str, []).extend(lines[start:end])

    # 写入归档文件
    for month, entry_lines in sorted(by_month.items()):
        archive_file = LOG_ARCHIVE / f"{month}.md"
        if archive_file.exists():
            existing = archive_file.read_text(encoding="utf-8")
            archive_file.write_text(existing + "".join(entry_lines), encoding="utf-8")
        else:
            archive_file.write_text("# Log Archive\n\n" + "".join(entry_lines), encoding="utf-8")
        print(f"  Archived {len(entry_lines)} lines → log-archive/{month}.md")

    # 从 log.md 删除已归档的行
    keep_ranges = []
    for idx in range(len(entries)):
        start = entries[idx][0]
        end = entries[idx + 1][0] if idx + 1 < len(entries) else len(lines)
        if idx not in archive_indices:
            keep_ranges.append((start, end))

    # 保留第一行（标题）+ 未归档条目
    new_lines = lines[:1]  # 标题行
    if lines[0].startswith("# "):
        # 找第一个非标题非空行之后的内容
        header_end = 1
        while header_end < len(lines) and lines[header_end].strip() == "":
            header_end += 1
        new_lines = lines[:header_end]

    for start, end in keep_ranges:
        new_lines.extend(lines[start:end])

    LOG.write_text("".join(new_lines), encoding="utf-8")
    print(f"\nDone. Archived {len(archive_indices)} entries, log.md: {total} → {len(new_lines)} lines")


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LLM Wiki 维护脚本")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fix-related", action="store_true", help="统一 related 为 [[wikilink]] 格式")
    group.add_argument("--rebuild-index", action="store_true", help="重建 index.md")
    group.add_argument("--log", metavar="MSG", help="追加 log.md 操作记录")
    group.add_argument("--lint", action="store_true", help="检测孤立页面和缺失引用")
    group.add_argument("--check-fm", action="store_true", help="检查 frontmatter 完整性")
    group.add_argument("--archive-log", action="store_true", help="归档半年前的日志条目")
    args = parser.parse_args()

    if args.fix_related:
        fix_related()
    elif args.rebuild_index:
        rebuild_index()
    elif args.log:
        append_log(args.log)
    elif args.lint:
        lint()
    elif args.check_fm:
        check_frontmatter()
    elif args.archive_log:
        archive_log()


if __name__ == "__main__":
    main()
