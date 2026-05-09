import aiosqlite
import os
from app.config import DATABASE_PATH


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")
    return db


async def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS buckets (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                slug        TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                telegram_chat_id TEXT NOT NULL DEFAULT '',
                forward_url TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                last_request_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id           TEXT PRIMARY KEY,
                bucket_id    TEXT NOT NULL,
                method       TEXT NOT NULL,
                path         TEXT NOT NULL DEFAULT '/',
                query_string TEXT NOT NULL DEFAULT '',
                headers      TEXT NOT NULL DEFAULT '{}',
                body         TEXT NOT NULL DEFAULT '',
                content_type TEXT NOT NULL DEFAULT '',
                client_ip    TEXT NOT NULL DEFAULT '',
                size_bytes   INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                FOREIGN KEY (bucket_id) REFERENCES buckets(id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS replays (
                id               TEXT PRIMARY KEY,
                request_id       TEXT NOT NULL,
                target_url       TEXT NOT NULL,
                method           TEXT NOT NULL,
                response_status  INTEGER,
                response_body    TEXT NOT NULL DEFAULT '',
                response_headers TEXT NOT NULL DEFAULT '{}',
                latency_ms       INTEGER NOT NULL DEFAULT 0,
                error            TEXT NOT NULL DEFAULT '',
                created_at       TEXT NOT NULL,
                FOREIGN KEY (request_id) REFERENCES requests(id) ON DELETE CASCADE
            )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_req_bucket  ON requests(bucket_id, created_at DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_req_created ON requests(created_at DESC)")
        await db.commit()
