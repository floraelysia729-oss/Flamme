"""Flamme 共享路径工具 — 所有脚本通过此模块获取 vault 路径。

目录结构约定：
    {source_dir}/.flamme/
    ├── converted/    ingest.py 输出的 .md
    ├── ocr/          薄页 PNG + OCR 文本
    ├── entities/     entity 页
    └── topics/       综述页
"""

import os
from pathlib import Path


def _detect_vault() -> Path:
    """优先用环境变量，否则从当前目录向上查找 .obsidian/"""
    env = os.environ.get("FLAMME_VAULT", "")
    if env:
        return Path(env)
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / ".obsidian").is_dir():
            return parent
    return current


VAULT = _detect_vault()


def flamme_dir(source_dir: Path) -> Path:
    """源文件夹对应的 .flamme/ 路径，如 pro/矩阵论 → pro/矩阵论/.flamme/"""
    d = source_dir / ".flamme"
    d.mkdir(parents=True, exist_ok=True)
    return d


def converted_dir(source_dir: Path) -> Path:
    d = flamme_dir(source_dir) / "converted"
    d.mkdir(exist_ok=True)
    return d


def ocr_dir(source_dir: Path) -> Path:
    d = flamme_dir(source_dir) / "ocr"
    d.mkdir(exist_ok=True)
    return d


def entities_dir(source_dir: Path) -> Path:
    d = flamme_dir(source_dir) / "entities"
    d.mkdir(exist_ok=True)
    return d


def topics_dir(source_dir: Path) -> Path:
    d = flamme_dir(source_dir) / "topics"
    d.mkdir(exist_ok=True)
    return d


def all_flamme_dirs() -> list[Path]:
    """扫描 vault 下所有 .flamme/ 目录"""
    return sorted(p for p in VAULT.rglob(".flamme") if p.is_dir())


def all_entity_files() -> set[str]:
    """扫描所有 .flamme/entities/ 下的 entity 名（去重）"""
    names = set()
    for fd in all_flamme_dirs():
        ed = fd / "entities"
        if ed.exists():
            names.update(f.stem for f in ed.glob("*.md"))
    return names


def source_dir_for_path(file_path: Path) -> Path:
    """给定 vault 内一个文件路径，返回它所属的源文件夹。

    pro/矩阵论/矩阵论.pdf → pro/矩阵论/
    pro/矩阵论/.flamme/converted/矩阵论.md → pro/矩阵论/
    """
    rel = file_path.resolve().relative_to(VAULT)
    parts = list(rel.parts)
    # 去掉 .flamme/ 及其子目录
    if ".flamme" in parts:
        idx = parts.index(".flamme")
        parts = parts[:idx]
        return VAULT.joinpath(*parts) if parts else VAULT
    # 普通文件：取父目录（去掉文件名），保留 level/name 结构
    if len(parts) >= 2:
        return VAULT.joinpath(*parts[:-1])
    return VAULT


def source_dir_from_vault_rel(rel_path: str) -> Path:
    """给定 vault 相对路径字符串，返回源文件夹。

    'pro/矩阵论/矩阵论.pdf' → VAULT / 'pro/矩阵论'
    """
    p = Path(rel_path)
    parts = p.parts
    if ".flamme" in parts:
        idx = parts.index(".flamme")
        return VAULT.joinpath(*parts[:idx]) if idx > 0 else VAULT
    if len(parts) >= 2:
        return VAULT.joinpath(*parts[:-1])
    return VAULT
