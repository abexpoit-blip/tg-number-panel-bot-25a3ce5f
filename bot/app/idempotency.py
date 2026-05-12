"""Persistent OTP idempotency helpers.

In-memory dedup resets whenever the bot container restarts. These helpers keep
a tiny DB-backed event key so old provider rows are not sent again after code
updates or console restarts.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .db import Otp


def otp_event_key(namespace: str, *parts: object) -> str:
    payload = "\x1f".join(str(part or "") for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
    return f"{namespace}:{digest}"


async def claim_otp_event(session: AsyncSession, event_key: str) -> bool:
    result = await session.execute(
        text(
            """
            INSERT INTO otp_delivery_events(event_key)
            VALUES (:event_key)
            ON CONFLICT (event_key) DO NOTHING
            """
        ),
        {"event_key": event_key[:128]},
    )
    return bool(result.rowcount)


async def otp_already_recorded(
    session: AsyncSession,
    *,
    phone: str,
    code: str,
    raw_text: str,
    matched_number_id: int | None,
) -> bool:
    stmt = select(Otp.id).where(Otp.code == code)
    if matched_number_id is not None:
        stmt = stmt.where(Otp.matched_number_id == matched_number_id)
    else:
        stmt = stmt.where(Otp.phone == phone, Otp.raw_text == raw_text)
    existing = (await session.execute(stmt.limit(1))).scalar_one_or_none()
    return existing is not None