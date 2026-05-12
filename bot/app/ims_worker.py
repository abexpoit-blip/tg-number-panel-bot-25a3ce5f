"""IMS bot worker — replaces the IPRN providers worker.

Runs up to TWO IMS accounts in parallel (settings prefixes `ims_` and `ims2_`).
On each tick it scrapes the IMS CDR table, matches incoming SMS rows to
assigned numbers (last-9-digit suffix + service keyword hint) and forwards
the OTP to the agent via `delivery.send_otp_message`.

All credentials, intervals and the master enable switch live in the
`settings` table so the admin can change them at runtime.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from .db import Country, Number, Otp, SessionLocal, Service, Setting, TgUser, get_setting
from .scrapers.ims import (
    DEFAULT_INTERVAL,
    MIN_INTERVAL_FLOOR,
    ImsClient,
    ImsLoginError,
    ImsRateLimited,
    ImsRow,
    ImsSessionLost,
)

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger("worker.ims")

ACCOUNTS = [
    {"label": "ims-1", "prefix": "ims"},
    {"label": "ims-2", "prefix": "ims2"},
]

# Last-N dedup so we never deliver the same row twice (per process).
class _Dedup:
    def __init__(self, cap: int = 5000) -> None:
        self._seen: set[str] = set()
        self._order: list[str] = []
        self._cap = cap

    def add(self, k: str) -> bool:
        if k in self._seen:
            return False
        self._seen.add(k)
        self._order.append(k)
        if len(self._order) > self._cap:
            old = self._order.pop(0)
            self._seen.discard(old)
        return True


_DEDUP = _Dedup()


def _service_slug_from_text(cli: str, msg: str) -> str | None:
    hay = f"{cli or ''} {msg or ''}".lower()
    pairs = [
        ("whatsapp", ("whatsapp", "whats app", "wa ")),
        ("facebook", ("facebook", "fb ", "meta")),
        ("telegram", ("telegram",)),
        ("instagram", ("instagram", "insta")),
        ("google", ("google", "gmail", "youtube")),
        ("tiktok", ("tiktok",)),
        ("twitter", ("twitter",)),
    ]
    for slug, needles in pairs:
        if any(n in hay for n in needles):
            return slug
    return None


async def _set_settings(prefix: str, defaults: dict[str, str]) -> None:
    """Seed missing keys so they appear in the admin Settings UI."""
    async with SessionLocal() as s:
        for k, v in defaults.items():
            row = (await s.execute(select(Setting).where(Setting.key == k))).scalar_one_or_none()
            if row is None:
                s.add(Setting(key=k, value=v))
        await s.commit()


async def _read_account_cfg(prefix: str) -> dict[str, str]:
    keys = [
        f"{prefix}_enabled", f"{prefix}_base_url",
        f"{prefix}_username", f"{prefix}_password",
        f"{prefix}_otp_interval", f"{prefix}_session_cookie",
        f"{prefix}_cookie_header",
    ]
    out: dict[str, str] = {}
    async with SessionLocal() as s:
        for k in keys:
            row = (await s.execute(select(Setting).where(Setting.key == k))).scalar_one_or_none()
            out[k] = (row.value if row else "") or ""
    return out


async def _save_session_cookie(prefix: str, cookie: str) -> None:
    if not cookie:
        return
    key = f"{prefix}_session_cookie"
    async with SessionLocal() as s:
        row = (await s.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
        if row:
            row.value = cookie
        else:
            s.add(Setting(key=key, value=cookie))
        await s.commit()


async def _match_number(phone: str, slug_hint: str | None) -> Number | None:
    """Find an assigned number matching by full phone or last-9-digit suffix.

    If a service slug hint is available (from CLI/message), prefer numbers
    whose service.keyword matches the slug.
    """
    tail = phone[-9:] if len(phone) >= 9 else phone
    async with SessionLocal() as s:
        candidates = (await s.execute(
            select(Number).where(
                Number.assigned_user_id.is_not(None),
                Number.phone.like(f"%{tail}"),
            )
        )).scalars().all()
        if not candidates:
            return None
        if slug_hint:
            for n in candidates:
                svc = (await s.execute(select(Service).where(Service.id == n.service_id))).scalar_one_or_none()
                if svc and slug_hint.lower() in (svc.keyword or "").lower():
                    return n
        # Fallback: first (and prefer exact phone match)
        exact = [n for n in candidates if n.phone == phone or n.phone.endswith(phone) or phone.endswith(n.phone)]
        return (exact or candidates)[0]


async def _deliver(bot: "Bot", row: ImsRow) -> None:
    code = row.extract_code()
    if not code:
        return
    if not _DEDUP.add(row.dedup_key()):
        return

    slug = _service_slug_from_text(row.cli, row.message)
    match = await _match_number(row.phone, slug)

    async with SessionLocal() as s:
        otp = Otp(
            phone=row.phone, code=code,
            raw_text=(row.message or "")[:1000],
            service_hint=row.cli or slug,
        )
        user: TgUser | None = None
        svc: Service | None = None
        ctry: Country | None = None
        if match:
            db_match = (await s.execute(select(Number).where(Number.id == match.id))).scalar_one()
            db_match.last_otp = code
            db_match.last_otp_at = datetime.utcnow()
            otp.matched_number_id = db_match.id
            otp.delivered_to_user_id = db_match.assigned_user_id
            user = (await s.execute(select(TgUser).where(TgUser.id == db_match.assigned_user_id))).scalar_one_or_none()
            svc = (await s.execute(select(Service).where(Service.id == db_match.service_id))).scalar_one_or_none()
            ctry = (await s.execute(select(Country).where(Country.id == db_match.country_id))).scalar_one_or_none()
        s.add(otp)
        await s.commit()

    if not (match and user and not user.is_banned):
        log.info("OTP %s for %s — no live assignment, parked", code, row.phone)
        return

    from .delivery import send_otp_message
    ok = await send_otp_message(user.tg_id, phone=row.phone, code=code, service=svc, country=ctry)
    if ok:
        log.info("✓ delivered OTP %s → tg=%s phone=%s", code, user.tg_id, row.phone)
    else:
        log.warning("delivery failed user=%s phone=%s", user.tg_id, row.phone)


async def _run_account(bot: "Bot", label: str, prefix: str) -> None:
    log.info("[%s] worker starting", label)
    await _set_settings(prefix, {
        f"{prefix}_enabled": "false",
        f"{prefix}_base_url": "https://www.imssms.org",
        f"{prefix}_username": "",
        f"{prefix}_password": "",
        f"{prefix}_otp_interval": str(DEFAULT_INTERVAL),
        f"{prefix}_session_cookie": "",
        f"{prefix}_cookie_header": "",
    })

    client: ImsClient | None = None
    consec_fail = 0

    while True:
        cfg = await _read_account_cfg(prefix)
        enabled = (cfg.get(f"{prefix}_enabled", "false") or "false").strip().lower() == "true"
        if not enabled:
            client = None
            await asyncio.sleep(15)
            continue

        try:
            interval = int(cfg.get(f"{prefix}_otp_interval") or DEFAULT_INTERVAL)
        except ValueError:
            interval = DEFAULT_INTERVAL
        interval = max(MIN_INTERVAL_FLOOR, interval)

        # (Re)build client when credentials change or first run
        if client is None or client.username != cfg[f"{prefix}_username"] \
                or client.password != cfg[f"{prefix}_password"] \
                or client.base_url.rstrip("/") != (cfg[f"{prefix}_base_url"] or "https://www.imssms.org").rstrip("/"):
            client = ImsClient(
                base_url=cfg[f"{prefix}_base_url"] or "https://www.imssms.org",
                username=cfg[f"{prefix}_username"],
                password=cfg[f"{prefix}_password"],
                session_cookie=cfg[f"{prefix}_session_cookie"],
                cookie_header=cfg[f"{prefix}_cookie_header"],
                interval=interval,
                label=label,
            )
        else:
            client.interval = interval

        try:
            if not client._logged_in:
                await client.login()
                await _save_session_cookie(prefix, client.current_session_cookie())
            rows = await client.fetch_cdr_rows()
            log.info("[%s] tick rows=%d", label, len(rows))
            for r in rows:
                try:
                    await _deliver(bot, r)
                except Exception as e:
                    log.exception("[%s] deliver failed: %s", label, e)
            consec_fail = 0
            await asyncio.sleep(max(MIN_INTERVAL_FLOOR, interval))
        except ImsRateLimited as e:
            penalty = client._register_penalty()
            log.warning("[%s] rate-limited: backing off %ss", label, penalty)
            await asyncio.sleep(penalty)
        except ImsSessionLost as e:
            log.warning("[%s] session lost — forcing relogin: %s", label, e)
            client._logged_in = False
            client._sesskey = None
            await asyncio.sleep(5)
        except ImsLoginError as e:
            consec_fail += 1
            log.error("[%s] login error: %s", label, e)
            await asyncio.sleep(min(300, 30 * consec_fail))
        except Exception as e:
            consec_fail += 1
            log.exception("[%s] tick error: %s", label, e)
            await asyncio.sleep(min(300, 10 + 5 * consec_fail))


async def ims_main(bot: "Bot") -> None:
    """Entry point: run all configured IMS accounts concurrently."""
    await asyncio.gather(*(
        _run_account(bot, a["label"], a["prefix"]) for a in ACCOUNTS
    ), return_exceptions=False)
