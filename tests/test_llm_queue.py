"""LLM Queue 并发测试"""

import time
import threading
from unittest.mock import MagicMock

from src.llm.queue import LLMQueue
from src.llm.provider import DefaultLLM
from src.llm.interfaces import LLMProvider


def test_queue_limits_concurrency():
    """验证队列正确限制并发数"""
    queue = LLMQueue(max_concurrency=2)
    active_count = 0
    max_active = 0
    lock = threading.Lock()

    def slow_task(task_id: int) -> str:
        nonlocal active_count, max_active
        with lock:
            active_count += 1
            max_active = max(max_active, active_count)
        time.sleep(0.1)
        with lock:
            active_count -= 1
        return f"result_{task_id}"

    results = [None] * 5
    threads = []
    for i in range(5):
        def run(idx=i):
            results[idx] = queue.run(slow_task, idx)
        t = threading.Thread(target=run)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert max_active <= 2, f"并发数超限: {max_active}"
    assert all(r is not None for r in results)


def test_queue_returns_results():
    """验证队列正确传递返回值"""
    queue = LLMQueue(max_concurrency=2)

    result = queue.run(lambda x: x * 2, 21)
    assert result == 42


def test_llm_provider_protocol():
    """验证 LLMProvider 满足 LLMProvider Protocol"""
    provider = DefaultLLM(api_key="test", base_url="https://fake.test")
    assert isinstance(provider, LLMProvider)
