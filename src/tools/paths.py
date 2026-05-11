"""Flamme 路径工具 — 替代 scripts/flamme_paths.py

提供 .flamme/ 目录结构管理，适配后端 Config 系统。
所有函数接收 vault_path 参数，不依赖全局变量。
"""

from pathlib import Path


def flamme_dir(source_dir: Path) -> Path:
    """源文件夹对应的 .flamme/ 路径"""
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


def all_flamme_dirs(vault_path: Path) -> list[Path]:
    """扫描 vault 下所有 .flamme/ 目录"""
    return sorted(p for p in vault_path.rglob(".flamme") if p.is_dir())


def all_entity_files(vault_path: Path) -> set[str]:
    """扫描所有 .flamme/entities/ 下的 entity 名"""
    names = set()
    for fd in all_flamme_dirs(vault_path):
        ed = fd / "entities"
        if ed.exists():
            names.update(f.stem for f in ed.glob("*.md"))
    return names


def source_dir_for_path(vault_path: Path, file_path: Path) -> Path:
    """文件路径 → 所属源文件夹

    pro/矩阵论/矩阵论.pdf → pro/矩阵论/
    """
    rel = file_path.resolve().relative_to(vault_path)
    parts = list(rel.parts)
    if ".flamme" in parts:
        idx = parts.index(".flamme")
        parts = parts[:idx]
        return vault_path.joinpath(*parts) if parts else vault_path
    if len(parts) >= 2:
        return vault_path.joinpath(*parts[:-1])
    return vault_path


def source_dir_from_vault_rel(vault_path: Path, rel_path: str) -> Path:
    """vault 相对路径 → 源文件夹"""
    p = Path(rel_path)
    parts = p.parts
    if ".flamme" in parts:
        idx = parts.index(".flamme")
        return vault_path.joinpath(*parts[:idx]) if idx > 0 else vault_path
    if len(parts) >= 2:
        return vault_path.joinpath(*parts[:-1])
    return vault_path
