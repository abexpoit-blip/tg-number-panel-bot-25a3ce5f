"""Admin broadcast notices.

Sends an HTML-formatted message to either bot users (DM), the configured
public feed channel(s), or both. Each send is logged in the `notices` table
with sent/failed counts so admins can review history.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Literal

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..config import settings
from ..db import get_db
from ..models import Setting, TgUser

log = logging.getLogger("api.notices")
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


async def _send_html(sess: aiohttp.ClientSession, chat_id: int, html: str) -> bool:
    res = await _tg(sess, "sendMessage", {
        "chat_id": chat_id,
        "text": html,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })
    return bool(res.get("ok"))


async def _channel_ids(db: AsyncSession) -> list[int]:
    row = (await db.execute(select(Setting).where(Setting.key == "public_feed_channel_ids"))).scalar_one_or_none()
    raw = (row.value if row else "") or ""
    out: list[int] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(int(chunk))
        except ValueError:
            pass
    return out


class NoticeIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    target: Literal["dm", "channel", "both"] = "both"


def _row(r) -> dict[str, Any]:
    return {
        "id": r.id,
        "text": r.text,
        "target": r.target,
        "sent_count": r.sent_count,
        "failed_count": r.failed_count,
        "total_targets": r.total_targets,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("")
async def list_notices(_: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(text(
        "SELECT id, text, target, sent_count, failed_count, total_targets, status, created_at "
        "FROM notices ORDER BY id DESC LIMIT 100"
    ))
    rows = res.mappings().all()
    return [
        {
            "id": r["id"],
            "text": r["text"],
            "target": r["target"],
            "sent_count": r["sent_count"],
            "failed_count": r["failed_count"],
            "total_targets": r["total_targets"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.post("/send")
async def send_notice(body: NoticeIn, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    if not settings.BOT_TOKEN:
        raise HTTPException(400, "BOT_TOKEN not configured")

    # Build target list
    dm_ids: list[int] = []
    if body.target in ("dm", "both"):
        rows = (await db.execute(
            select(TgUser.tg_id).where(TgUser.is_banned == False)  # noqa: E712
        )).scalars().all()
        dm_ids = [int(t) for t in rows if t]

    ch_ids: list[int] = []
    if body.target in ("channel", "both"):
        ch_ids = await _channel_ids(db)

    total = len(dm_ids) + len(ch_ids)

    # Insert pending notice row
    ins = await db.execute(text(
        "INSERT INTO notices (text, target, sent_count, failed_count, total_targets, status, created_at) "
        "VALUES (:t, :tg, 0, 0, :n, 'sending', :ts) RETURNING id"
    ), {"t": body.text, "tg": body.target, "n": total, "ts": datetime.utcnow()})
    notice_id = ins.scalar_one()
    await db.commit()

    sent = 0
    failed = 0
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        # channels first (small list, may be priority)
        for cid in ch_ids:
            ok = await _send_html(sess, cid, body.text)
            if ok:
                sent += 1
            else:
                failed += 1

        # DM batch with light pacing to respect Telegram's ~30/sec limit.
        BATCH = 25
        for i in range(0, len(dm_ids), BATCH):
            chunk = dm_ids[i:i + BATCH]
            results = await asyncio.gather(*[_send_html(sess, uid, body.text) for uid in chunk])
            sent += sum(1 for ok in results if ok)
            failed += sum(1 for ok in results if not ok)
            if i + BATCH < len(dm_ids):
                await asyncio.sleep(1.0)

    await db.execute(text(
        "UPDATE notices SET sent_count=:s, failed_count=:f, status='done' WHERE id=:i"
    ), {"s": sent, "f": failed, "i": notice_id})
    await db.commit()

    return {"id": notice_id, "sent": sent, "failed": failed, "total": total}
