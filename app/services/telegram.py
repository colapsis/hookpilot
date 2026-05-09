import httpx
from app.config import TELEGRAM_BOT_TOKEN


async def send_notification(
    chat_id: str,
    bucket_name: str,
    method: str,
    path: str,
    size_bytes: int,
) -> None:
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return

    text = (
        f"🔔 *New webhook — {bucket_name}*\n"
        f"`{method} {path}`\n"
        f"Size: {size_bytes} bytes"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            })
    except Exception:
        pass
