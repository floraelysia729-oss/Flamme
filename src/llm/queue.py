"""LLM 并发队列 — 控制同时发送的请求数

TS 映射: 同名 class, Promise 替代 Semaphore
"""

import threading
from typing import Callable


class LLMQueue:
    """线程安全的并发队列 — 限制同时执行的 LLM 请求数"""

    def __init__(self, max_concurrency: int = 2):
        self._semaphore = threading.Semaphore(max_concurrency)
        self._max_concurrency = max_concurrency

    def run(self, fn: Callable, *args, **kwargs) -> object:
        """入队并同步执行 fn，自动控制并发数

        TS 映射: async run(fn) => Promise
        """
        self._semaphore.acquire()
        try:
            return fn(*args, **kwargs)
        finally:
            self._semaphore.release()

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency
