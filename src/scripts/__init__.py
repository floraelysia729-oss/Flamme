"""Scripts 适配层 — 提供旧脚本需要的全局变量和便捷导入。

旧脚本用 `from flamme_paths import VAULT` 等，
这里提供兼容接口，自动从 config 获取 vault 路径。
"""

from pathlib import Path
from src.tools.paths import (
    flamme_dir, converted_dir, ocr_dir, entities_dir, topics_dir,
    all_flamme_dirs, all_entity_files, source_dir_for_path, source_dir_from_vault_rel,
)
from src.config import detect_vault as _detect_vault


VAULT = Path(_detect_vault())
