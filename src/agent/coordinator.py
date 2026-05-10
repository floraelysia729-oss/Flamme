"""Coordinator 编排器 — Worker Pool 模式

管理任务拆解和 Worker 并行执行：
  intent → 任务拆解 → task_queue → Workers 并行执行 → 汇总结果

简单任务（status/single query）仍走 Agent.run() 快速返回。

TS 映射: 同名 class, Worker 替换为 Worker Thread / Worker Process
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.agent.agent import Agent
from src.agent.workers import IngestWorker, QueryWorker, LintWorker, BatchTagWorker
from src.agent.worker import BaseWorker
from src.db.client import SQLiteClient
from src.tools.registry import ToolRegistry


class Coordinator:
    """多 Agent 编排器 — 管理任务拆解和 Worker Pool

    角色分工：
    - brain_llm (GLM 5.1): 编排决策、任务拆解、结果汇总
    - llm (DeepSeek): Worker 执行时的 chat 补全
    - embed (千问): 向量嵌入（通过 llm/embedding_store）
    """

    def __init__(self, agent: Agent, db: SQLiteClient, tools: ToolRegistry,
                 llm=None, brain_llm=None, embedding_store=None, llm_queue=None,
                 max_workers: int = 3):
        self._agent = agent
        self._db = db
        self._tools = tools
        self._llm = llm              # Worker 用（DeepSeek）
        self._brain_llm = brain_llm  # 编排大脑（GLM）
        self._embedding_store = embedding_store
        self._llm_queue = llm_queue
        self._max_workers = max_workers

        # worker 类型注册表
        self._worker_classes: dict[str, type[BaseWorker]] = {
            "ingest": IngestWorker,
            "query": QueryWorker,
            "lint": LintWorker,
            "batch_tag": BatchTagWorker,
        }

    def run(self, prompt: str, **kwargs) -> str:
        """委托给 Agent 执行（兼容旧调用方式）"""
        return self._agent.run(prompt, **kwargs)

    def _run_workers(self, task_ids: list[int]) -> list[dict]:
        """启动 Worker Pool 执行任务"""
        # 确定需要哪些 worker 类型
        pending = self._db.get_tasks_by_status("claimed") + self._db.get_tasks_by_status("pending")
        types_needed = set(t["type"] for t in pending if t["id"] in task_ids)

        # 准备 worker 类型（每个线程内创建独立 SQLite 连接，避免跨线程复用连接）
        worker_types = [task_type for task_type in types_needed if task_type in self._worker_classes]
        if not worker_types:
            return []

        def _run_worker(worker_type: str) -> list[dict]:
            worker_cls = self._worker_classes[worker_type]
            worker_db = SQLiteClient(self._db._db_path, vault_path=self._db._vault_path)
            try:
                worker = worker_cls(
                    worker_id=f"worker-{worker_type}",
                    db=worker_db,
                    tools=self._tools,
                    llm=self._llm,
                    embedding_store=self._embedding_store,
                    llm_queue=self._llm_queue,
                )
                return worker.run_loop()
            finally:
                worker_db.close()

        # 线程池执行
        all_results = []
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(worker_types))) as pool:
            futures = {pool.submit(_run_worker, worker_type): worker_type for worker_type in worker_types}
            for future in as_completed(futures):
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    all_results.append({
                        "_error": str(e),
                        "_status": "failed",
                        "type": futures[future],
                    })

        return all_results

    def _summarize(self, results: list[dict]) -> str:
        """汇总 Worker 执行结果"""
        if not results:
            return "无任务执行"

        done = [r for r in results if r.get("_status") == "done"]
        failed = [r for r in results if r.get("_status") == "failed"]

        lines = [f"任务完成: {len(done)} 成功, {len(failed)} 失败"]
        for r in done:
            result_text = r.get("_result", "")
            lines.append(f"  ✓ [{r.get('type', '?')}] {result_text}")
        for r in failed:
            lines.append(f"  ✗ [{r.get('type', '?')}] {r.get('_error', '未知错误')}")

        return "\n".join(lines)

    def run_single(self, prompt: str, **kwargs) -> str:
        """单 Agent 模式（不经过 Worker Pool）"""
        return self._agent.run(prompt, **kwargs)

    def dispatch(self, worker_type: str, payload: dict) -> int:
        """派发任务到指定 Worker 类型，返回 task_id

        用于 Orchestrator → Worker 模式。
        """
        task_id = self._db.push_task(worker_type, payload, generation=0)
        # 启动一个单次 worker 执行
        worker_cls = self._worker_classes.get(worker_type)
        if not worker_cls:
            raise ValueError(f"未知 Worker 类型: {worker_type}")

        # 在 worker 线程内创建 SQLiteClient（避免跨线程使用）
        thread = threading.Thread(
            target=self._run_single_task,
            args=(worker_cls, worker_type, task_id),
            daemon=True,
        )
        thread.start()
        return task_id

    def dispatch_batch(self, worker_type: str, payloads: list[dict]) -> list[int]:
        """批量派发同类型任务，启动 Worker Pool 消费，返回 task_ids"""
        if not payloads:
            return []

        task_ids = []
        for payload in payloads:
            tid = self._db.push_task(worker_type, payload, generation=0)
            task_ids.append(tid)

        # 后台线程跑 Worker Pool
        thread = threading.Thread(
            target=self._run_workers,
            args=(task_ids,),
            daemon=True,
        )
        thread.start()
        return task_ids

    def wait_for_batch(self, task_ids: list[int], timeout: float = 600,
                       poll_interval: float = 2.0) -> list[dict]:
        """等待批量任务全部完成"""
        start = time.time()
        remaining = set(task_ids)
        results = {}

        while remaining and time.time() - start < timeout:
            for tid in list(remaining):
                row = self._db._conn.execute(
                    "SELECT status, payload FROM task_queue WHERE id = ?", (tid,)
                ).fetchone()
                if not row:
                    results[tid] = {"error": f"任务不存在: {tid}"}
                    remaining.discard(tid)
                elif row["status"] in ("done", "failed"):
                    payload = json.loads(row["payload"]) if row["payload"] else {}
                    if row["status"] == "done":
                        results[tid] = payload.get("result", payload)
                    else:
                        results[tid] = {"error": payload.get("_error", "任务失败")}
                    remaining.discard(tid)
            if remaining:
                time.sleep(poll_interval)

        # 超时未完成的
        for tid in remaining:
            results[tid] = {"error": "超时"}

        return [results.get(tid, {"error": "未知"}) for tid in task_ids]

    def wait_for(self, task_id: int, timeout: float = 120) -> dict:
        """等待任务完成，返回结果

        轮询 task_queue 状态直到 done/failed 或超时。
        """
        start = time.time()
        while time.time() - start < timeout:
            # 查询任务状态
            row = self._db._conn.execute(
                "SELECT status, payload FROM task_queue WHERE id = ?", (task_id,)
            ).fetchone()
            if not row:
                return {"error": f"任务不存在: {task_id}"}

            status = row["status"]
            if status == "done":
                import json
                payload = json.loads(row["payload"]) if row["payload"] else {}
                return payload.get("result", payload)
            elif status == "failed":
                import json
                payload = json.loads(row["payload"]) if row["payload"] else {}
                return {"error": payload.get("_error", "任务失败")}

            time.sleep(0.5)

        row = self._db._conn.execute(
            "SELECT status, claimed_by FROM task_queue WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row:
            return {
                "error": f"任务超时 ({timeout}s)",
                "task_id": task_id,
                "status": row["status"],
                "claimed_by": row["claimed_by"],
            }
        return {"error": f"任务超时 ({timeout}s)", "task_id": task_id}

    def _run_single_task(self, worker_cls, worker_type: str, task_id: int):
        """在后台线程中执行单个 worker 任务（连接在此线程内创建）"""
        from src.db.client import SQLiteClient
        worker_db = SQLiteClient(self._db._db_path, vault_path=self._db._vault_path)
        try:
            worker = worker_cls(
                worker_id=f"orch-{worker_type}-{task_id}",
                db=worker_db,
                tools=self._tools,
                llm=self._llm,
                embedding_store=self._embedding_store,
                llm_queue=self._llm_queue,
            )
            result = worker.run_task(task_id)
            if result is None:
                row = worker_db._conn.execute(
                    "SELECT status FROM task_queue WHERE id = ?",
                    (task_id,),
                ).fetchone()
                if row and row["status"] in ("pending", "claimed"):
                    worker_db.fail_task(task_id, "目标任务未被执行（认领失败）")
        finally:
            worker_db.close()
