"""Flamme 路径工具 — 替代 scripts/flamme_paths.py

源文件夹级 .flamme/ 仅保留 converted/、ocr/ 等中间产物。
Vault 根级 wiki 页（entity/topic/comparison/exploration）放在可见目录。
"""

from pathlib import Path

WIKI_PAGE_DIRS = {
    "entity": "entities",
    "topic": "topics",
    "comparison": "comparisons",
    "exploration": "explorations",
}

LEGACY_WIKI_SUBDIRS = ("topics", "comparisons", "explorations", "entities")


def flamme_dir(source_dir: Path) -> Path:
    """源文件夹对应的 .flamme/ 路径（converted/ocr 中间产物）"""
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


def entities_dir(vault_path: Path) -> Path:
    """Vault 级 entity 目录 — vault/entities/"""
    d = vault_path / "entities"
    d.mkdir(parents=True, exist_ok=True)
    return d


def page_type_dir(vault_path: Path, page_type: str) -> Path:
    """Vault 级 wiki 页目录 — vault/{entities|topics|...}/"""
    subdir = WIKI_PAGE_DIRS.get(page_type, "topics")
    d = vault_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def topics_dir(vault_path: Path) -> Path:
    return page_type_dir(vault_path, "topic")


def comparisons_dir(vault_path: Path) -> Path:
    return page_type_dir(vault_path, "comparison")


def explorations_dir(vault_path: Path) -> Path:
    return page_type_dir(vault_path, "exploration")


def all_flamme_dirs(vault_path: Path) -> list[Path]:
    """扫描 vault 下所有源文件夹级 .flamme/ 目录"""
    return sorted(p for p in vault_path.rglob(".flamme") if p.is_dir())


def all_wiki_page_files(vault_path: Path) -> list[Path]:
    """扫描 vault 根下 entities/topics/comparisons/explorations 中的 .md"""
    files: list[Path] = []
    for sub in WIKI_PAGE_DIRS.values():
        d = vault_path / sub
        if d.is_dir():
            files.extend(sorted(d.glob("*.md")))
    return files


def all_entity_files(vault_path: Path) -> set[str]:
    """扫描 vault/entities/ 下的 entity 名"""
    ed = entities_dir(vault_path)
    if ed.exists():
        return {f.stem for f in ed.glob("*.md")}
    return set()


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
