from __future__ import annotations

_CACHE = {}

STATS = {"hits": 0, "misses": 0}


def get(signature):
    compiled = _CACHE.get(signature)
    if compiled is None:
        STATS["misses"] += 1
    else:
        STATS["hits"] += 1
    return compiled


def put(signature, compiled):
    _CACHE[signature] = compiled
    return compiled


def size():
    return len(_CACHE)


def clear():
    _CACHE.clear()
    STATS["hits"] = 0
    STATS["misses"] = 0


__all__ = ["STATS", "clear", "get", "put", "size"]
