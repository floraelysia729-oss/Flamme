"""Git 操作封装 — 使用 subprocess 调用 git

依赖 Obsidian 已装载的 Git 插件进行自动 commit
TS 映射: simple-git npm 包
"""

import subprocess
from pathlib import Path


class GitHelper:
    """Git 操作封装"""

    def __init__(self, repo_path: str):
        self._repo_path = repo_path

    def get_head_commit(self) -> str:
        """获取当前 HEAD commit hash"""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git rev-parse failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def commit(self, message: str) -> None:
        """git add all + commit"""
        subprocess.run(
            ["git", "add", "-A"],
            cwd=self._repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message, "--allow-empty"],
            cwd=self._repo_path,
            capture_output=True,
            check=True,
        )

    def is_clean(self) -> bool:
        """检查工作区是否干净"""
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() == ""

    def get_repo_path(self) -> str:
        return self._repo_path
