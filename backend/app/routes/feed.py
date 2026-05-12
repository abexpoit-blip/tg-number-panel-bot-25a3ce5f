"""Public OTP feed channel inspector.

Reads the comma-separated `public_feed_channel_ids` setting and queries
Telegram for live status (title + member count + admin permission) so the
admin panel can show what's wired up.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..config import settings
from ..db import get_db
from ..models import Otp, Setting

log = logging.getLogger("api.feed")
router = APIRouter()

API_BASE = "https://api.telegram.org"


async def _tg(sess: aiohttp.ClientSession, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN not configured"}
    url = f"{API_BASE}/bot{settings.BOT_TOKEN}/{method}"
    try:
        async with sess.post(url, json=payload) as r:
            return await r.json(content_type=None)
    except Exception as e:
        return {"ok": False, "description": str(e)}


async def _channel_status(sess: aiohttp.ClientSession, chat_id: int) -> dict[str, Any]:
    chat = await _tg(sess, "getChat", {"chat_id": chat_id})
    if not chat.get("ok"):
        return {"id": chat_id, "ok": False, "error": chat.get("description") or "getChat failed"}
    info = chat["result"]
    members = await _tg(sess, "getChatMemberCount", {"chat_id": chat_id})
    return {
        "id": chat_id,
        "ok": True,
        "title": info.get("title") or info.get("username") or str(chat_id),
        "username": info.get("username"),
        "type": info.get("type"),
        "members": (members.get("result") if members.get("ok") else None),
        "error": None,
    }


@router.get("/channels")
async def list_feed_channels(
    _: object = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Setting).where(Setting.key == "public_feed_channel_ids"))).scalar_one_or_none()
    raw = (row.value if row else "") or ""
    ids: list[int] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            pass

    # Total OTPs ever forwarded (across all assigned numbers) — quick health metric.
    total_otps = (await db.execute(select(func.count(Otp.id)))).scalar() or 0

    if not ids:
        return {"channels": [], "raw": raw, "total_otps": total_otps}

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        results = await asyncio.gather(*[_channel_status(sess, cid) for cid in ids])
    return {"channels": results, "raw": raw, "total_otps": total_otps}
