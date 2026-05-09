import httpx
import time
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

from app.database import get_db

# Headers that must not be forwarded
_HOP_BY_HOP = {
    "host", "connection", "transfer-encoding", "te",
    "trailer", "upgrade", "proxy-authorization", "proxy-authenticate",
    "content-length",  # httpx sets this from the body
}


async def do_replay(
    request_id: str,
    target_url: str,
    override_headers: Optional[dict] = None,
    override_body: Optional[str] = None,
) -> dict:
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return {"error": "Request not found"}

        req = dict(row)
        method = req["method"]
        headers = json.loads(req["headers"])
        body = req["body"]

        # Apply overrides
        if override_headers:
            headers.update(override_headers)
        if override_body is not None:
            body = override_body

        # Strip hop-by-hop headers
        headers = {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}

        start = time.monotonic()
        error = ""
        status = None
        resp_body = ""
        resp_headers = {}

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.request(
                    method=method,
                    url=target_url,
                    headers=headers,
                    content=body.encode("utf-8") if body else b"",
                )
            latency_ms = int((time.monotonic() - start) * 1000)
            status = response.status_code
            resp_headers = dict(response.headers)
            try:
                resp_body = response.text[:10_000]
            except Exception:
                resp_body = "[unreadable response]"
        except httpx.TimeoutException:
            latency_ms = int((time.monotonic() - start) * 1000)
            error = "Request timed out after 15 seconds"
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            error = str(exc)

        replay_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await db.execute("""
            INSERT INTO replays (id, request_id, target_url, method, response_status,
                                 response_body, response_headers, latency_ms, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            replay_id, request_id, target_url, method,
            status, resp_body, json.dumps(resp_headers),
            latency_ms, error, now,
        ))
        await db.commit()

        return {
            "id": replay_id,
            "status": status,
            "latency_ms": latency_ms,
            "error": error,
            "response_body": resp_body,
            "response_headers": resp_headers,
        }
    finally:
        await db.close()


async def forward_request(
    target_url: str,
    method: str,
    headers: dict,
    body_bytes: bytes,
    query_string: str,
) -> None:
    """Fire-and-forget auto-forward to a configured URL."""
    clean_headers = {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}
    url = f"{target_url}?{query_string}" if query_string else target_url
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.request(
                method=method,
                url=url,
                headers=clean_headers,
                content=body_bytes,
            )
    except Exception:
        pass
