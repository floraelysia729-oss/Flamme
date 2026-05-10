"""断点续传管理 — 读写 checkpoints 表，支持操作中断后恢复

TS 映射: 同名 class, SQLite client 方法一一对应
"""

from src.db.client import SQLiteClient
from src.infra.git_helper import GitHelper


class CheckpointManager:
    """断点续传 — 操作开始写 checkpoint，完成时标记 done"""

    def __init__(self, db: SQLiteClient, git: GitHelper):
        self._db = db
        self._git = git

    def start(self, operation: str, target: str, snapshot: dict) -> int:
        """开始一个操作，返回 checkpoint id"""
        commit = self._git.get_head_commit()
        return self._db.create_checkpoint(operation, target, snapshot, commit)

    def update(self, checkpoint_id: int, snapshot: dict) -> None:
        """更新中间状态"""
        self._db.update_checkpoint(checkpoint_id, snapshot)

    def complete(self, checkpoint_id: int) -> None:
        """标记完成"""
        self._db.complete_checkpoint(checkpoint_id)

    def find_pending(self, operation: str) -> dict | None:
        """查找未完成的操作，返回 checkpoint 记录（含 snapshot）"""
        pending = self._db.find_pending_checkpoint(operation)
        if pending is None:
            return None

        # 检查 git commit 是否匹配
        current_commit = self._git.get_head_commit()
        if pending["git_commit"] != current_commit:
            return {
                **pending,
                "commit_mismatch": True,
                "expected_commit": pending["git_commit"],
                "current_commit": current_commit,
            }

        return pending

    def run_with_checkpoint(self, operation: str, target: str, items: list, process_fn) -> dict:
        """带断点续传的批量操作

        process_fn(item) -> bool: 处理单个 item，返回是否成功
        返回 {"processed": int, "failed": int, "resumed": bool}
        """
        resumed = False
        pending = self.find_pending(operation)

        if pending and not pending.get("commit_mismatch"):
            # 从断点恢复
            snapshot = pending["snapshot"]
            cp_id = pending["id"]
            processed_set = set(snapshot.get("files_processed", []))
            remaining = [i for i in items if str(i) not in processed_set]
            resumed = True
        else:
            # 新操作
            cp_id = self.start(operation, target, {"files_processed": [], "files_failed": []})
            remaining = items
            processed_set = set()

        processed = len(processed_set)
        failed = 0

        for item in remaining:
            try:
                success = process_fn(item)
                if success:
                    processed_set.add(str(item))
                    processed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

            # 每 10 个更新一次 checkpoint
            if (processed + failed) % 10 == 0:
                self.update(cp_id, {
                    "files_processed": list(processed_set),
                    "files_failed": [],
                })

        # 最终更新
        self.update(cp_id, {
            "files_processed": list(processed_set),
            "files_failed": [],
        })
        self.complete(cp_id)

        return {"processed": processed, "failed": failed, "resumed": resumed}
