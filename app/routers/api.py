import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.database import get_db
from app import events
from app.services.replay import do_replay

router = APIRouter(prefix="/api")


# ── helpers ────────────────────────────────────────────────────────────────

def _slug_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "bucket"


# ── Bucket CRUD ────────────────────────────────────────────────────────────

class BucketCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: str = ""
    telegram_chat_id: str = ""
    forward_url: str = ""


class BucketUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    forward_url: Optional[str] = None


@router.post("/buckets")
async def create_bucket(body: BucketCreate):
    slug = body.slug or _slug_from_name(body.name)
    slug = re.sub(r"[^a-z0-9\-]", "", slug.lower()).strip("-") or "bucket"

    db = await get_db()
    try:
        async with db.execute("SELECT id FROM buckets WHERE slug = ?", (slug,)) as cur:
            if await cur.fetchone():
                raise HTTPException(400, f"Slug '{slug}' already taken")

        bucket_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.execute("""
            INSERT INTO buckets (id, name, slug, description, telegram_chat_id, forward_url, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (bucket_id, body.name, slug, body.description,
              body.telegram_chat_id, body.forward_url, now))
        await db.commit()
        return {"id": bucket_id, "slug": slug, "name": body.name}
    finally:
        await db.close()


@router.patch("/buckets/{slug}")
async def update_bucket(slug: str, body: BucketUpdate):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM buckets WHERE slug = ?", (slug,)) as cur:
            bucket = await cur.fetchone()
        if not bucket:
            raise HTTPException(404, "Bucket not found")

        bucket = dict(bucket)
        updates = {}
        if body.name is not None:
            updates["name"] = body.name
        if body.description is not None:
            updates["description"] = body.description
        if body.telegram_chat_id is not None:
            updates["telegram_chat_id"] = body.telegram_chat_id
        if body.forward_url is not None:
            updates["forward_url"] = body.forward_url

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            await db.execute(
                f"UPDATE buckets SET {set_clause} WHERE slug = ?",
                [*updates.values(), slug],
            )
            await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@router.delete("/buckets/{slug}")
async def delete_bucket(slug: str):
    db = await get_db()
    try:
        async with db.execute("SELECT id FROM buckets WHERE slug = ?", (slug,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Bucket not found")
        await db.execute("DELETE FROM buckets WHERE slug = ?", (slug,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ── Requests ───────────────────────────────────────────────────────────────

@router.get("/buckets/{slug}/requests")
async def list_requests(slug: str, limit: int = 50, offset: int = 0):
    db = await get_db()
    try:
        async with db.execute("SELECT id FROM buckets WHERE slug = ?", (slug,)) as cur:
            bucket = await cur.fetchone()
        if not bucket:
            raise HTTPException(404, "Bucket not found")

        async with db.execute("""
            SELECT id, method, path, query_string, content_type,
                   client_ip, size_bytes, created_at
            FROM requests
            WHERE bucket_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (bucket["id"], limit, offset)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

        return {"requests": rows}
    finally:
        await db.close()


@router.get("/requests/{request_id}")
async def get_request(request_id: str):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Request not found")

        req = dict(row)
        req["headers"] = json.loads(req["headers"])

        async with db.execute("""
            SELECT id, target_url, method, response_status, latency_ms, error, created_at
            FROM replays WHERE request_id = ? ORDER BY created_at DESC
        """, (request_id,)) as cur:
            req["replays"] = [dict(r) for r in await cur.fetchall()]

        return req
    finally:
        await db.close()


@router.delete("/requests/{request_id}")
async def delete_request(request_id: str):
    db = await get_db()
    try:
        async with db.execute("DELETE FROM requests WHERE id = ?", (request_id,)) as cur:
            if cur.rowcount == 0:
                raise HTTPException(404, "Request not found")
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@router.get("/requests/{request_id}/curl")
async def export_curl(request_id: str):
    db = await get_db()
    try:
        async with db.execute("""
            SELECT r.*, b.slug FROM requests r
            JOIN buckets b ON b.id = r.bucket_id
            WHERE r.id = ?
        """, (request_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Request not found")

        req = dict(row)
        headers = json.loads(req["headers"])
        parts = [f"curl -X {req['method']}"]

        for k, v in headers.items():
            safe_v = v.replace("'", "'\"'\"'")
            parts.append(f"  -H '{k}: {safe_v}'")

        if req["body"] and req["method"] not in ("GET", "HEAD"):
            safe_body = req["body"].replace("'", "'\"'\"'")
            parts.append(f"  -d '{safe_body}'")

        qs = f"?{req['query_string']}" if req["query_string"] else ""
        parts.append(f"  '{req['path']}{qs}'")

        return {"curl": " \\\n".join(parts)}
    finally:
        await db.close()


# ── Replay ─────────────────────────────────────────────────────────────────

class ReplayRequest(BaseModel):
    target_url: str
    override_headers: Optional[dict] = None
    override_body: Optional[str] = None


@router.post("/requests/{request_id}/replay")
async def replay_request(request_id: str, body: ReplayRequest):
    result = await do_replay(
        request_id=request_id,
        target_url=body.target_url,
        override_headers=body.override_headers,
        override_body=body.override_body,
    )
    return result


# ── SSE stream ─────────────────────────────────────────────────────────────

import asyncio


@router.get("/stream/{slug}")
async def sse_stream(slug: str):
    async def generator():
        q = events.subscribe(slug)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            events.unsubscribe(slug, q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Stats ──────────────────────────────────────────────────────────────────

@router.get("/stats")
async def global_stats():
    db = await get_db()
    try:
        async with db.execute("SELECT COUNT(*) FROM buckets") as cur:
            buckets = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM requests") as cur:
            total = (await cur.fetchone())[0]
        today = datetime.now(timezone.utc).date().isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM requests WHERE created_at >= ?", (today,)
        ) as cur:
            today_count = (await cur.fetchone())[0]
        return {"buckets": buckets, "total_requests": total, "today": today_count}
    finally:
        await db.close()
