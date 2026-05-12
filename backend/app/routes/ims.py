"""IMS scraper admin endpoints — test login + last status snapshot.

All credentials live in the `settings` table under the `ims_*` (account #1)
and `ims2_*` (account #2) prefixes. The bot worker reads them at runtime.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..db import get_db
from ..models import Setting

router = APIRouter()

ACCOUNTS = {"1": "ims", "2": "ims2"}


def _import_client():
    """Import the bot scraper without forcing api container to ship aiogram."""
    try:
        from app_scrapers.ims import ImsClient  # type: ignore
    except Exception:
        from ..scrapers_ims import ImsClient  # type: ignore
    return ImsClient


async def _get_settings(db: AsyncSession, prefix: str) -> dict[str, str]:
    keys = [
        f"{prefix}_enabled", f"{prefix}_base_url",
        f"{prefix}_username", f"{prefix}_password",
        f"{prefix}_otp_interval", f"{prefix}_session_cookie",
        f"{prefix}_cookie_header",
    ]
    out: dict[str, str] = {}
    for k in keys:
        row = (await db.execute(select(Setting).where(Setting.key == k))).scalar_one_or_none()
        out[k] = (row.value if row else "") or ""
    return out


@router.get("/accounts")
async def list_accounts(_: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    """Mask sensitive fields and return both IMS account configurations."""
    out = []
    for slot, prefix in ACCOUNTS.items():
        s = await _get_settings(db, prefix)
        out.append({
            "slot": slot,
            "prefix": prefix,
            "enabled": (s.get(f"{prefix}_enabled", "false") or "false").lower() == "true",
            "base_url": s.get(f"{prefix}_base_url") or "https://www.imssms.org",
            "username": s.get(f"{prefix}_username") or "",
            "has_password": bool(s.get(f"{prefix}_password")),
            "otp_interval": int(s.get(f"{prefix}_otp_interval") or 18),
            "has_session_cookie": bool(s.get(f"{prefix}_session_cookie")),
            "has_cookie_header": bool(s.get(f"{prefix}_cookie_header")),
        })
    return out


@router.post("/{slot}/test")
async def test_account(slot: str, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    if slot not in ACCOUNTS:
        raise HTTPException(404, "unknown slot")
    prefix = ACCOUNTS[slot]
    cfg = await _get_settings(db, prefix)
    ImsClient = _import_client()
    client = ImsClient(
        base_url=cfg.get(f"{prefix}_base_url") or "https://www.imssms.org",
        username=cfg.get(f"{prefix}_username") or "",
        password=cfg.get(f"{prefix}_password") or "",
        session_cookie=cfg.get(f"{prefix}_session_cookie") or "",
        cookie_header=cfg.get(f"{prefix}_cookie_header") or "",
        interval=int(cfg.get(f"{prefix}_otp_interval") or 18),
        label=f"ims-{slot}-test",
    )
    try:
        await client.login(force_captcha=False)
        rows = await client.fetch_cdr_rows()
        # persist refreshed PHPSESSID for fast bot restarts
        sess = client.current_session_cookie()
        if sess:
            row = (await db.execute(select(Setting).where(Setting.key == f"{prefix}_session_cookie"))).scalar_one_or_none()
            if row:
                row.value = sess
            else:
                db.add(Setting(key=f"{prefix}_session_cookie", value=sess))
            await db.commit()
        return {"ok": True, "rows_seen": len(rows), "session_saved": bool(sess)}
    except Exception as e:
        raise HTTPException(400, detail=f"{type(e).__name__}: {e}")
