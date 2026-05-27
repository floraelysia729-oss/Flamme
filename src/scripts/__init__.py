"""Scripts 适配层 — 提供旧脚本需要的全局变量和便捷导入。

旧脚本用 `from flamme_paths import VAULT` 等，
这里提供兼容接口，自动从 config 获取 vault 路径。
"""

from pathlib import Path
from src.tools.paths import (
    flamme_dir, converted_dir, ocr_dir, entities_dir, topics_dir,
    comparisons_dir, explorations_dir, page_type_dir,
    all_flamme_dirs, all_entity_files, all_wiki_page_files,
    source_dir_for_path, source_dir_from_vault_rel,
)
from src.config import detect_vault as _detect_vault


class _LazyVault:
    """延迟初始化 VAULT — 首次使用时才调 detect_vault()，避免模块导入时触发 warning

    代理 Path 的所有属性，对外行为与 Path 一致。
    """
    def __init__(self):
        self.__dict__["_path"]: Path | None = None

    def _resolve(self) -> Path:
        if self.__dict__["_path"] is None:
            self.__dict__["_path"] = Path(_detect_vault())
        return self.__dict__["_path"]

    def __str__(self):
        return str(self._resolve())

    def __repr__(self):
        return repr(self._resolve())

    def __fspath__(self):
        return str(self._resolve())

    def __truediv__(self, other):
        return self._resolve() / other

    def __rtruediv__(self, other):
        return other / self._resolve()

    def __bool__(self):
        return bool(self._resolve())

    def __eq__(self, other):
        return self._resolve() == other

    def __hash__(self):
        return hash(self._resolve())

    def __getattr__(self, name):
        return getattr(self._resolve(), name)


VAULT = _LazyVault()
