"""Worker 基类 — 从 task_queue 消费任务并执行

子类只需实现 _execute_task(payload) 方法。

TS 映射: 同名 abstract class
"""

import logging

from src.agent.interfaces import WorkerProtocol
from src.db.client import SQLiteClient

logger = logging.getLogger(__name__)


class BaseWorker:
    """Worker 基类 — claim → execute → complete/fail 生命周期"""

    def __init__(self, worker_id: str, db: SQLiteClient, tools=None, llm=None,
                 embedding_store=None, llm_queue=None):
        self._worker_id = worker_id
        self._db = db
        self._tools = tools
        self._llm = llm
        self._embedding_store = embedding_store
        self._llm_queue = llm_queue

    @property
    def worker_type(self) -> str:
        """该 Worker 能处理的任务类型（子类必须覆盖）"""
        raise NotImplementedError

    def execute(self, task: dict) -> str:
        """执行单个任务

        Args:
            task: task_queue 行（payload 已反序列化为 dict）
        Returns:
            结果文本
        """
        payload = task.get("payload", {})
        return self._execute_task(payload)

    def _execute_task(self, payload: dict) -> str:
        """子类实现具体任务逻辑"""
        raise NotImplementedError

    def run_once(self) -> dict | None:
        """认领并执行一个任务

        Returns:
            执行的任务 dict，或 None（无可用任务）
        """
        task = self._db.claim_task(self._worker_id, self.worker_type)
        if task is None:
            return None

        return self._run_claimed_task(task)

    def run_task(self, task_id: int) -> dict | None:
        """认领并执行指定 task_id（仅执行该任务）"""
        task = self._db.claim_task_by_id(self._worker_id, task_id, self.worker_type)
        if task is None:
            return None

        return self._run_claimed_task(task)

    def _run_claimed_task(self, task: dict) -> dict:
        """执行已认领任务并落库状态"""
        try:
            result_text = self.execute(task)
            self._db.complete_task(task["id"], {"result": result_text})
            task["_result"] = result_text
            task["_status"] = "done"
            logger.info(
                "Worker[%s] task %s done (type=%s)",
                self._worker_id,
                task.get("id"),
                task.get("type"),
            )
        except Exception as e:
            self._db.fail_task(task["id"], str(e))
            task["_error"] = str(e)
            task["_status"] = "failed"
            logger.exception(
                "Worker[%s] task %s failed (type=%s): %s",
                self._worker_id,
                task.get("id"),
                task.get("type"),
                e,
            )

        return task

    def run_loop(self, max_tasks: int = 0, poll_interval: float = 0.5,
                 max_empty_waits: int = 2) -> list[dict]:
        """循环认领并执行任务，队列为空时短暂等待后重试

        Args:
            max_tasks: 最多执行 N 个任务，0 = 不限
            poll_interval: 队列空时等待秒数
            max_empty_waits: 连续空队列最大次数，达到后退出
        Returns:
            执行过的任务列表
        """
        import time
        results = []
        empty_count = 0
        while True:
            if max_tasks and len(results) >= max_tasks:
                break
            task = self.run_once()
            if task is None:
                empty_count += 1
                if empty_count >= max_empty_waits:
                    break
                time.sleep(poll_interval)
                continue
            empty_count = 0
            results.append(task)
        return results

    def _call_llm(self, fn, *args, **kwargs):
        """通过并发队列调用 LLM"""
        if self._llm_queue:
            return self._llm_queue.run(fn, *args, **kwargs)
        return fn(*args, **kwargs)

    def _tool_exec(self, tool, params: dict) -> dict:
        """执行工具并返回 dict（兼容 ToolResult 和旧 dict）"""
        result = tool.execute(params)
        from src.tools.interfaces import ToolResult
        if isinstance(result, ToolResult):
            if result.is_error:
                return {"error": result.error}
            return result.data if isinstance(result.data, dict) else {"result": result.data}
        return result if isinstance(result, dict) else {"result": result}
