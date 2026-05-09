import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import DATABASE_PATH, MAX_BODY_SIZE, MAX_REQUESTS_PER_BUCKET
from app.database import get_db
from app import events
from app.services.telegram import send_notification
from app.services.replay import forward_request

router = APIRouter()

_SKIP_HEADERS = {"host", "connection", "transfer-encoding"}


@router.api_route(
    "/w/{slug}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def capture_webhook(slug: str, request: Request):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM buckets WHERE slug = ?", (slug,)) as cur:
            bucket = await cur.fetchone()

        if not bucket:
            return JSONResponse(
                {"error": f"Bucket '{slug}' not found. Create it at the dashboard."},
                status_code=404,
            )

        bucket = dict(bucket)

        # Read body with size cap
        body_bytes = await request.body()
        truncated = len(body_bytes) > MAX_BODY_SIZE
        if truncated:
            body_bytes = body_bytes[:MAX_BODY_SIZE]

        try:
            body_str = body_bytes.decode("utf-8")
        except UnicodeDecodeError:
            body_str = f"[binary: {len(body_bytes)} bytes]"

        if truncated:
            body_str += f"\n\n[... truncated at {MAX_BODY_SIZE // 1024} KB]"

        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in _SKIP_HEADERS
        }

        req_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        client_ip = request.client.host if request.client else ""

        await db.execute("""
            INSERT INTO requests
              (id, bucket_id, method, path, query_string, headers, body,
               content_type, client_ip, size_bytes, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            req_id,
            bucket["id"],
            request.method,
            request.url.path,
            str(request.url.query),
            json.dumps(headers),
            body_str,
            request.headers.get("content-type", ""),
            client_ip,
            len(body_bytes),
            now,
        ))

        # Enforce per-bucket request cap (delete oldest over limit)
        await db.execute("""
            DELETE FROM requests
            WHERE bucket_id = ? AND id NOT IN (
                SELECT id FROM requests
                WHERE bucket_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            )
        """, (bucket["id"], bucket["id"], MAX_REQUESTS_PER_BUCKET))

        await db.execute(
            "UPDATE buckets SET last_request_at = ? WHERE id = ?",
            (now, bucket["id"]),
        )
        await db.commit()
    finally:
        await db.close()

    # SSE push
    asyncio.create_task(events.push(slug, {
        "id": req_id,
        "method": request.method,
        "path": request.url.path,
        "created_at": now,
        "size_bytes": len(body_bytes),
        "client_ip": client_ip,
        "content_type": request.headers.get("content-type", ""),
    }))

    # Telegram (optional)
    if bucket.get("telegram_chat_id"):
        asyncio.create_task(send_notification(
            bucket["telegram_chat_id"],
            bucket["name"],
            request.method,
            request.url.path,
            len(body_bytes),
        ))

    # Auto-forward (optional)
    if bucket.get("forward_url"):
        asyncio.create_task(forward_request(
            bucket["forward_url"],
            request.method,
            headers,
            body_bytes,
            str(request.url.query),
        ))

    return JSONResponse({"ok": True, "id": req_id}, status_code=200)
