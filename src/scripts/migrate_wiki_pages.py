"""Wiki 页迁移脚本 — 将 .flamme/{topics,comparisons,explorations} 搬到 vault 根可见目录

用法:
  python -m src.scripts.migrate_wiki_pages <vault_path> [--dry-run] [--cleanup] [--update-db]
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from src.tools.paths import LEGACY_WIKI_SUBDIRS


def _rel(vault: Path, p: Path) -> str:
    return str(p.relative_to(vault)).replace("\\", "/")


def migrate_wiki_pages(
    vault_path: Path,
    dry_run: bool = False,
    cleanup: bool = False,
    update_db: bool = False,
) -> None:
    """扫描 vault 下 .flamme/{topics,comparisons,explorations[,entities]}，迁移到 vault 根目录"""
    moved = 0
    skipped = 0
    conflicts = 0
    db_updated = 0
    source_flamme_dirs: set[Path] = set()
    virtual_dest: dict[str, set[str]] = {s: set() for s in LEGACY_WIKI_SUBDIRS if s != "entities"}

    for flamme_dir in sorted(vault_path.rglob(".flamme")):
        if not flamme_dir.is_dir():
            continue
        for subdir in LEGACY_WIKI_SUBDIRS:
            if subdir == "entities":
                continue  # 由 migrate_entities.py 处理
            src_dir = flamme_dir / subdir
            if not src_dir.is_dir():
                continue
            source_flamme_dirs.add(flamme_dir)
            dest_dir = vault_path / subdir

            for src_file in sorted(src_dir.glob("*.md")):
                dest_file = dest_dir / src_file.name
                already = dest_file.exists() or src_file.name in virtual_dest[subdir]

                if already:
                    if dest_file.exists():
                        if src_file.stat().st_mtime <= dest_file.stat().st_mtime:
                            print(f"  [skip] {src_file.name} (dest is newer)")
                            skipped += 1
                            continue
                        print(f"  [conflict→overwrite] {_rel(vault_path, src_file)} (newer)")
                        conflicts += 1
                    else:
                        print(f"  [conflict→overwrite] {_rel(vault_path, src_file)} (同名覆盖)")
                        conflicts += 1

                old_rel = _rel(vault_path, src_file)
                new_rel = f"{subdir}/{src_file.name}"

                if dry_run:
                    print(f"  [copy] {old_rel} → {new_rel}")
                else:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dest_file)
                    src_file.unlink()
                    print(f"  [copied] {old_rel} → {new_rel}")
                    if update_db:
                        db_updated += _rewrite_db_path(vault_path, old_rel, new_rel)

                virtual_dest[subdir].add(src_file.name)
                moved += 1

    print(f"\n结果: {moved} 迁移, {skipped} 跳过, {conflicts} 覆盖")
    if update_db and not dry_run:
        print(f"DB 路径更新: {db_updated} 条")

    if cleanup and not dry_run:
        cleaned = 0
        for flamme_dir in sorted(source_flamme_dirs):
            for subdir in LEGACY_WIKI_SUBDIRS:
                sub = flamme_dir / subdir
                if sub.is_dir() and not any(sub.iterdir()):
                    sub.rmdir()
                    print(f"  [cleanup] {_rel(vault_path, sub)}")
            if flamme_dir.exists() and not any(flamme_dir.iterdir()):
                flamme_dir.rmdir()
                print(f"  [cleanup] {_rel(vault_path, flamme_dir)}")
                cleaned += 1
        print(f"清理: {cleaned} 个空 .flamme 目录")


def _rewrite_db_path(vault_path: Path, old_rel: str, new_rel: str) -> int:
    db_path = vault_path / ".wiki" / "knowledge.db"
    if not db_path.is_file():
        return 0
    from src.db.client import SQLiteClient

    db = SQLiteClient(str(db_path))
    try:
        doc = db.get_document(old_rel)
        if not doc:
            return 0
        db.delete_document(old_rel)
        doc["path"] = new_rel
        db.put_document(doc)
        return 1
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="迁移 .flamme/{topics,comparisons,explorations} → vault 根可见目录",
    )
    parser.add_argument("vault_path", help="Vault 根目录路径")
    parser.add_argument("--dry-run", action="store_true", help="只输出计划，不执行")
    parser.add_argument("--cleanup", action="store_true", help="迁移后清理空的 .flamme 子目录")
    parser.add_argument("--update-db", action="store_true", help="同步更新 SQLite 中的文档路径")
    args = parser.parse_args()

    vault = Path(args.vault_path)
    if not vault.is_dir():
        print(f"错误: {vault} 不是有效目录")
        sys.exit(1)

    print(f"Vault: {vault}")
    if args.dry_run:
        print("模式: dry-run（仅预览）")
    print()

    migrate_wiki_pages(
        vault,
        dry_run=args.dry_run,
        cleanup=args.cleanup,
        update_db=args.update_db,
    )


if __name__ == "__main__":
    main()
