import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    def __init__(self, max_entries: int = 256, ttl_seconds: int = 300):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._values: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: Any) -> Any | None:
        cache_key = stable_cache_key(key)
        with self._lock:
            item = self._values.get(cache_key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= time.monotonic():
                self._values.pop(cache_key, None)
                return None
            self._values.move_to_end(cache_key)
            return copy.deepcopy(value)

    def set(self, key: Any, value: Any) -> None:
        cache_key = stable_cache_key(key)
        with self._lock:
            self._values[cache_key] = (time.monotonic() + self.ttl_seconds, copy.deepcopy(value))
            self._values.move_to_end(cache_key)
            while len(self._values) > self.max_entries:
                self._values.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._values)


def stable_cache_key(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


embedding_cache = TTLCache(max_entries=512, ttl_seconds=3600)
retrieval_cache = TTLCache(max_entries=512, ttl_seconds=300)
semantic_response_cache = TTLCache(max_entries=256, ttl_seconds=300)
