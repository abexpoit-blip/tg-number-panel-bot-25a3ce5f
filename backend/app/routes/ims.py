"""IMS scraper admin endpoints — control + monitor.

All credentials live in the `settings` table under the `ims_*` (account #1)
and `ims2_*` (account #2) prefixes. The bot worker reads them at runtime
and publishes a live status JSON back to `{prefix}_status`.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..db import get_db
from ..models import Setting

router = APIRouter()

ACCOUNTS = {"1": "ims", "2": "ims2"}

# Whitelisted keys that admin can update via /ims/{slot}/config
EDITABLE_KEYS = {
    "base_url", "username", "password",
    "otp_interval", "cookie_header", "session_cookie",
}

DEFAULTS = {
    "base_url": "https://www.imssms.org",
    "otp_interval": "18",
}


def _import_client():
    """Import the bot scraper without forcing api container to ship aiogram."""
    try:
        from app_scrapers.ims import ImsClient  # type: ignore
    except Exception:
        from ..scrapers_ims import ImsClient  # type: ignore
    return ImsClient


async def _get(db: AsyncSession, key: str) -> str:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    return (row.value if row else "") or ""


async def _put(db: AsyncSession, key: str, value: str) -> None:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    await db.commit()


async def _get_account(db: AsyncSession, prefix: str) -> dict:
    keys = [
        f"{prefix}_enabled", f"{prefix}_base_url",
        f"{prefix}_username", f"{prefix}_password",
        f"{prefix}_otp_interval", f"{prefix}_session_cookie",
        f"{prefix}_cookie_header", f"{prefix}_status",
    ]
    out: dict[str, str] = {}
    for k in keys:
        out[k] = await _get(db, k)
    status = None
    raw = out.get(f"{prefix}_status") or ""
    if raw:
        try:
            status = json.loads(raw)
        except Exception:
            status = None
    return {
        "enabled": (out.get(f"{prefix}_enabled", "false") or "false").lower() == "true",
        "base_url": out.get(f"{prefix}_base_url") or DEFAULTS["base_url"],
        "username": out.get(f"{prefix}_username") or "",
        "has_password": bool(out.get(f"{prefix}_password")),
        "otp_interval": int(out.get(f"{prefix}_otp_interval") or DEFAULTS["otp_interval"]),
        "has_session_cookie": bool(out.get(f"{prefix}_session_cookie")),
        "has_cookie_header": bool(out.get(f"{prefix}_cookie_header")),
        "status": status,
    }


@router.get("/accounts")
async def list_accounts(_: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    """Return both IMS account configurations + live worker status snapshot."""
    out = []
    for slot, prefix in ACCOUNTS.items():
        a = await _get_account(db, prefix)
        a.update({"slot": slot, "prefix": prefix})
        out.append(a)
    return out


class ToggleIn(BaseModel):
    enabled: bool


@router.post("/{slot}/toggle")
async def toggle_account(slot: str, body: ToggleIn,
                         _: object = Depends(current_admin),
                         db: AsyncSession = Depends(get_db)):
    if slot not in ACCOUNTS:
        raise HTTPException(404, "unknown slot")
    prefix = ACCOUNTS[slot]
    await _put(db, f"{prefix}_enabled", "true" if body.enabled else "false")
    return {"ok": True, "enabled": body.enabled}


class ConfigIn(BaseModel):
    base_url: str | None = None
    username: str | None = None
    password: str | None = None
    otp_interval: int | None = None
    cookie_header: str | None = None
    session_cookie: str | None = None


@router.put("/{slot}/config")
async def update_config(slot: str, body: ConfigIn,
                        _: object = Depends(current_admin),
                        db: AsyncSession = Depends(get_db)):
    if slot not in ACCOUNTS:
        raise HTTPException(404, "unknown slot")
    prefix = ACCOUNTS[slot]
    payload = body.model_dump(exclude_none=True)
    for k, v in payload.items():
        if k not in EDITABLE_KEYS:
            continue
        if k == "otp_interval":
            iv = max(16, int(v))
            await _put(db, f"{prefix}_{k}", str(iv))
        else:
            await _put(db, f"{prefix}_{k}", str(v))
    return {"ok": True, "updated": list(payload.keys())}


@router.post("/{slot}/clear-session")
async def clear_session(slot: str, _: object = Depends(current_admin),
                        db: AsyncSession = Depends(get_db)):
    """Wipe stored PHPSESSID. Worker will solve captcha + relogin on next tick."""
    if slot not in ACCOUNTS:
        raise HTTPException(404, "unknown slot")
    prefix = ACCOUNTS[slot]
    await _put(db, f"{prefix}_session_cookie", "")
    await _put(db, f"{prefix}_clear_session", "true")
    return {"ok": True}


@router.post("/{slot}/relogin")
async def force_relogin(slot: str, _: object = Depends(current_admin),
                        db: AsyncSession = Depends(get_db)):
    """Ask the worker to reauthenticate on its next tick (cookie kept)."""
    if slot not in ACCOUNTS:
        raise HTTPException(404, "unknown slot")
    prefix = ACCOUNTS[slot]
    await _put(db, f"{prefix}_force_relogin", "true")
    return {"ok": True}


@router.post("/{slot}/test")
async def test_account(slot: str, _: object = Depends(current_admin),
                       db: AsyncSession = Depends(get_db)):
    if slot not in ACCOUNTS:
        raise HTTPException(404, "unknown slot")
    prefix = ACCOUNTS[slot]
    cfg_keys = [
        f"{prefix}_base_url", f"{prefix}_username", f"{prefix}_password",
        f"{prefix}_session_cookie", f"{prefix}_cookie_header", f"{prefix}_otp_interval",
    ]
    cfg = {k: await _get(db, k) for k in cfg_keys}
    ImsClient = _import_client()
    client = ImsClient(
        base_url=cfg.get(f"{prefix}_base_url") or DEFAULTS["base_url"],
        username=cfg.get(f"{prefix}_username") or "",
        password=cfg.get(f"{prefix}_password") or "",
        session_cookie=cfg.get(f"{prefix}_session_cookie") or "",
        cookie_header=cfg.get(f"{prefix}_cookie_header") or "",
        interval=int(cfg.get(f"{prefix}_otp_interval") or DEFAULTS["otp_interval"]),
        label=f"ims-{slot}-test",
    )
    try:
        await client.login(force_captcha=False)
        rows = await client.fetch_cdr_rows()
        sess = client.current_session_cookie()
        if sess:
            await _put(db, f"{prefix}_session_cookie", sess)
        return {"ok": True, "rows_seen": len(rows), "session_saved": bool(sess)}
    except Exception as e:
        raise HTTPException(400, detail=f"{type(e).__name__}: {e}")
