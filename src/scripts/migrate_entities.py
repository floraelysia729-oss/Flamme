"""Entity 迁移脚本 — 将 .flamme/entities/*.md 搬到 vault/entities/

用法:
  python -m src.scripts.migrate_entities <vault_path> [--dry-run] [--cleanup]
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)


def migrate_entities(vault_path: Path, dry_run: bool = False, cleanup: bool = False) -> None:
    """扫描 vault 下所有 .flamme/entities/，迁移到 vault/entities/"""
    dest_dir = vault_path / "entities"
    moved = 0
    skipped = 0
    conflicts = 0
    source_dirs: list[Path] = []
    virtual_dest: set[str] = set()  # dry-run 追踪已处理的文件名

    # 扫描所有 .flamme/entities/ 目录
    for flamme_dir in sorted(vault_path.rglob(".flamme")):
        ent_dir = flamme_dir / "entities"
        if not ent_dir.is_dir():
            continue
        source_dirs.append(ent_dir)

        for src_file in sorted(ent_dir.glob("*.md")):
            dest_file = dest_dir / src_file.name
            already_exists = dest_file.exists() or src_file.name in virtual_dest

            if already_exists:
                # 同名冲突
                if dest_file.exists():
                    # 实际存在的文件：比较时间戳
                    src_mtime = src_file.stat().st_mtime
                    dst_mtime = dest_file.stat().st_mtime
                    if src_mtime > dst_mtime:
                        print(f"  [conflict→overwrite] {src_file.relative_to(vault_path)} (newer)")
                        conflicts += 1
                    else:
                        print(f"  [skip] {src_file.name} (dest is newer)")
                        skipped += 1
                        continue
                else:
                    # dry-run 中虚拟冲突：后者覆盖前者
                    print(f"  [conflict→overwrite] {src_file.relative_to(vault_path)} (同名覆盖)")
                    conflicts += 1
                continue

            if dry_run:
                print(f"  [copy] {src_file.relative_to(vault_path)} → entities/{src_file.name}")
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)
                print(f"  [copied] {src_file.name}")
            virtual_dest.add(src_file.name)
            moved += 1

    print(f"\n结果: {moved} 迁移, {skipped} 跳过, {conflicts} 覆盖")

    # 清理空的 .flamme/entities/ 目录
    if cleanup and not dry_run:
        cleaned = 0
        for ent_dir in source_dirs:
            remaining = list(ent_dir.iterdir())
            if not remaining:
                ent_dir.rmdir()
                flamme_dir = ent_dir.parent
                # 如果 .flamme/ 也空了，一并清理
                if not list(flamme_dir.iterdir()):
                    flamme_dir.rmdir()
                    print(f"  [cleanup] {flamme_dir.relative_to(vault_path)}")
                else:
                    print(f"  [cleanup] {ent_dir.relative_to(vault_path)}")
                cleaned += 1
        print(f"清理: {cleaned} 个空目录")


def main():
    parser = argparse.ArgumentParser(description="迁移 .flamme/entities/ → vault/entities/")
    parser.add_argument("vault_path", help="Vault 根目录路径")
    parser.add_argument("--dry-run", action="store_true", help="只输出计划，不执行")
    parser.add_argument("--cleanup", action="store_true", help="迁移后清理空的 .flamme/entities/ 目录")
    args = parser.parse_args()

    vault = Path(args.vault_path)
    if not vault.is_dir():
        print(f"错误: {vault} 不是有效目录")
        sys.exit(1)

    print(f"Vault: {vault}")
    if args.dry_run:
        print("模式: dry-run（仅预览）")
    print()

    migrate_entities(vault, dry_run=args.dry_run, cleanup=args.cleanup)


if __name__ == "__main__":
    main()
