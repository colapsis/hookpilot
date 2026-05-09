"""In-process SSE event bus — no Redis needed."""
import asyncio
from typing import Dict, List

_queues: Dict[str, List[asyncio.Queue]] = {}


def subscribe(slug: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _queues.setdefault(slug, []).append(q)
    return q


def unsubscribe(slug: str, q: asyncio.Queue) -> None:
    bucket_qs = _queues.get(slug, [])
    try:
        bucket_qs.remove(q)
    except ValueError:
        pass


async def push(slug: str, data: dict) -> None:
    for q in list(_queues.get(slug, [])):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass
