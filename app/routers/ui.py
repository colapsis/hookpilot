import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.config import BASE_URL

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _pretty_json(text: str) -> str:
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except Exception:
        return text


def _method_color(method: str) -> str:
    return {
        "GET":     "bg-blue-500",
        "POST":    "bg-green-500",
        "PUT":     "bg-amber-500",
        "PATCH":   "bg-purple-500",
        "DELETE":  "bg-red-500",
        "HEAD":    "bg-slate-500",
        "OPTIONS": "bg-teal-500",
    }.get(method.upper(), "bg-slate-500")


def _status_color(status: int | None) -> str:
    if status is None:
        return "text-slate-400"
    if status < 300:
        return "text-green-400"
    if status < 400:
        return "text-amber-400"
    return "text-red-400"


templates.env.globals["method_color"] = _method_color
templates.env.globals["status_color"] = _status_color
templates.env.globals["base_url"] = BASE_URL
templates.env.filters["pretty_json"] = _pretty_json


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = await get_db()
    try:
        async with db.execute("""
            SELECT b.*,
                   COUNT(r.id) AS request_count
            FROM buckets b
            LEFT JOIN requests r ON r.bucket_id = b.id
            GROUP BY b.id
            ORDER BY b.last_request_at DESC NULLS LAST, b.created_at DESC
        """) as cur:
            buckets = [dict(row) for row in await cur.fetchall()]

        async with db.execute("SELECT COUNT(*) FROM requests") as cur:
            total_requests = (await cur.fetchone())[0]

        today = datetime.now(timezone.utc).date().isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM requests WHERE created_at >= ?", (today,)
        ) as cur:
            today_requests = (await cur.fetchone())[0]
    finally:
        await db.close()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "buckets": buckets,
        "total_requests": total_requests,
        "today_requests": today_requests,
    })


@router.get("/b/{slug}", response_class=HTMLResponse)
async def bucket_view(request: Request, slug: str):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM buckets WHERE slug = ?", (slug,)) as cur:
            bucket = await cur.fetchone()
        if not bucket:
            raise HTTPException(404, f"Bucket '{slug}' not found")

        bucket = dict(bucket)

        async with db.execute("""
            SELECT id, method, path, query_string, content_type,
                   client_ip, size_bytes, created_at
            FROM requests
            WHERE bucket_id = ?
            ORDER BY created_at DESC
            LIMIT 100
        """, (bucket["id"],)) as cur:
            reqs = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT COUNT(*) FROM requests WHERE bucket_id = ?", (bucket["id"],)
        ) as cur:
            total = (await cur.fetchone())[0]
    finally:
        await db.close()

    return templates.TemplateResponse("bucket.html", {
        "request": request,
        "bucket": bucket,
        "requests": reqs,
        "total": total,
        "webhook_url": f"{BASE_URL}/w/{slug}",
    })


@router.get("/r/{request_id}", response_class=HTMLResponse)
async def request_detail(request: Request, request_id: str):
    db = await get_db()
    try:
        async with db.execute("""
            SELECT r.*, b.slug, b.name as bucket_name
            FROM requests r JOIN buckets b ON b.id = r.bucket_id
            WHERE r.id = ?
        """, (request_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Request not found")

        req = dict(row)
        req["headers_parsed"] = json.loads(req["headers"])
        req["query_parsed"] = dict(
            pair.split("=", 1) if "=" in pair else (pair, "")
            for pair in req["query_string"].split("&")
            if pair
        )

        try:
            req["body_pretty"] = json.dumps(json.loads(req["body"]), indent=2)
            req["body_is_json"] = True
        except Exception:
            req["body_pretty"] = req["body"]
            req["body_is_json"] = False

        async with db.execute("""
            SELECT * FROM replays WHERE request_id = ? ORDER BY created_at DESC
        """, (request_id,)) as cur:
            replays = [dict(r) for r in await cur.fetchall()]
        for rp in replays:
            rp["response_headers"] = json.loads(rp["response_headers"])
    finally:
        await db.close()

    return templates.TemplateResponse("request.html", {
        "request": request,
        "req": req,
        "replays": replays,
        "webhook_url": f"{BASE_URL}/w/{req['slug']}",
    })
