"""Git 操作封装 — 使用 subprocess 调用 git

依赖 Obsidian 已装载的 Git 插件进行自动 commit
TS 映射: simple-git npm 包
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitFileChange:
    status: str   # M, A, D, R, ?, etc.
    path: str     # vault 相对路径（正斜杠）


class GitHelper:
    """Git 操作封装"""

    def __init__(self, repo_path: str):
        self._repo_path = repo_path

    def is_repo(self) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

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

    def status_porcelain(self) -> list[GitFileChange]:
        """工作区变更（含未跟踪文件）"""
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        changes: list[GitFileChange] = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            raw_path = line[3:].strip()
            if " -> " in raw_path:
                raw_path = raw_path.split(" -> ", 1)[1]
            status = xy.strip() or "?"
            changes.append(GitFileChange(status=status, path=raw_path.replace("\\", "/")))
        return changes

    def diff_name_only(self, base_ref: str, head_ref: str = "HEAD") -> list[str]:
        """base..head 之间变更的文件路径列表"""
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [p.strip().replace("\\", "/") for p in result.stdout.splitlines() if p.strip()]

    def changed_paths_since(self, commit: str) -> set[str]:
        """自指定 commit 以来有变更的路径（含工作区未提交变更）"""
        paths = set(self.diff_name_only(commit))
        for ch in self.status_porcelain():
            paths.add(ch.path)
        return paths
