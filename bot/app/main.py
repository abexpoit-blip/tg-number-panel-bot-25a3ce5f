"""Telegram bot — user-facing menu + OTP feed listener in one process."""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from sqlalchemy import func, select

from .config import settings
from .db import Base, Country, CountryRange, Number, Otp, Service, SessionLocal, TgUser, engine
from .emoji import flag_emoji_html, service_emoji_html
from .parser import parse_message
from .ims_worker import ims_main

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bot")

bot: Bot | None = None
dp = Dispatcher()


@dp.errors()
async def on_error(event):
    """Catch-all so a single handler crash never silently kills the bot."""
    log.exception("Handler crashed: %s", event.exception)
    try:
        upd = event.update
        msg = getattr(upd, "message", None) or getattr(getattr(upd, "callback_query", None), "message", None)
        if msg:
            await msg.answer("⚠️ Something went wrong. Please try again.")
    except Exception:
        pass
    return True


async def init_db() -> None:
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in [
            "ALTER TABLE services  ADD COLUMN IF NOT EXISTS custom_emoji_id VARCHAR(64)",
            "ALTER TABLE countries ADD COLUMN IF NOT EXISTS custom_emoji_id VARCHAR(64)",
            "ALTER TABLE numbers  ADD COLUMN IF NOT EXISTS provider_id INTEGER REFERENCES providers(id) ON DELETE SET NULL",
            "ALTER TABLE otps     ADD COLUMN IF NOT EXISTS provider_id INTEGER REFERENCES providers(id) ON DELETE SET NULL",
            "ALTER TABLE numbers  ADD COLUMN IF NOT EXISTS range_id INTEGER REFERENCES country_ranges(id) ON DELETE SET NULL",
            "CREATE INDEX IF NOT EXISTS ix_numbers_range_id ON numbers(range_id)",
            "ALTER TABLE numbers DROP CONSTRAINT IF EXISTS uq_phone_service",
            "DROP INDEX IF EXISTS uq_phone_service",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_phone_service_range ON numbers(phone, service_id, country_id, range_id) WHERE range_id IS NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_phone_service_norange ON numbers(phone, service_id, country_id) WHERE range_id IS NULL",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass


def copy_button(text: str, value: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, copy_text=CopyTextButton(text=value[:256]))


def emoji_html(svc: Service | None) -> str:
    """Render Telegram premium custom emoji when configured, fallback to unicode."""
    return service_emoji_html(svc)


def flag_html(c: Country | None) -> str:
    """Render Telegram premium flag emoji when configured, fallback to unicode flag."""
    return flag_emoji_html(c)


_BRAND_EMOJI = {
    "whatsapp": "🟢", "wa": "🟢",
    "facebook": "🔵", "fb": "🔵",
    "instagram": "🟣", "ig": "🟣",
    "telegram": "✈️", "tg": "✈️",
    "tiktok": "🎵", "tt": "🎵",
    "twitter": "🐦", "x": "🐦",
    "google": "🔴", "gmail": "📧",
    "discord": "💬", "signal": "📞",
    "viber": "🟪", "wechat": "💚", "line": "💚",
    "snapchat": "👻", "youtube": "📺",
}


def _brand_emoji_for(sv: Service) -> str | None:
    key = f"{(getattr(sv, 'keyword', '') or '')} {(sv.name or '')}".lower()
    for k, v in _BRAND_EMOJI.items():
        if k in key:
            return v
    return None


def service_btn_emoji(sv: Service) -> str:
    """Pick a simple unicode emoji for the inline button based on icon_mode.

    Modes: custom (use sv.emoji) | brand (auto pick from brand map) | default (📱) | auto (custom > brand > default).
    Premium custom emojis don't render inside Telegram inline buttons, so we always
    use a plain unicode glyph here.
    """
    mode = (getattr(sv, "icon_mode", None) or "auto").lower()
    raw = (getattr(sv, "emoji", None) or "").strip()
    brand = _brand_emoji_for(sv)
    if mode == "custom":
        return raw or "📱"
    if mode == "brand":
        return brand or raw or "📱"
    if mode == "default":
        return "📱"
    # auto
    if raw and raw != "📱":
        return raw
    return brand or "📱"


def svc_button(sv: Service) -> InlineKeyboardButton:
    emo = service_btn_emoji(sv)
    nm = (sv.name or "Service").strip()
    return InlineKeyboardButton(text=f"{emo} {nm}", callback_data=f"svc:{sv.id}")



# ============= UI =============

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 Get Number"), KeyboardButton(text="💰 Balance")],
            [KeyboardButton(text="📊 Status"), KeyboardButton(text="🌍 Available Country")],
        ],
        resize_keyboard=True,
    )


async def ensure_user(msg_user) -> TgUser:
    async with SessionLocal() as s:
        u = (await s.execute(select(TgUser).where(TgUser.tg_id == msg_user.id))).scalar_one_or_none()
        if not u:
            u = TgUser(tg_id=msg_user.id, username=msg_user.username, first_name=msg_user.first_name)
            s.add(u)
            await s.commit()
            await s.refresh(u)
        return u


# ============= Commands =============

@dp.message(CommandStart())
async def on_start(msg: Message):
    u = await ensure_user(msg.from_user)
    if u.is_banned:
        await msg.answer("⛔ You are banned.")
        return
    name = msg.from_user.first_name or "friend"
    inline_kb = None
    if settings.WEBAPP_URL:
        from aiogram.types import WebAppInfo
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✨ Open Premium Menu", web_app=WebAppInfo(url=settings.WEBAPP_URL))
        ]])
    await msg.answer(
        f"👋 <b>Welcome {name}!</b> ✊\n\n🟢 <b>Main Menu</b>\n📥 Please select an option below:",
        reply_markup=main_menu_kb(),
    )
    if inline_kb:
        await msg.answer("Tap below for the premium-style menu with branded icons:", reply_markup=inline_kb)


@dp.message(F.text == "💰 Balance")
async def on_balance(msg: Message):
    u = await ensure_user(msg.from_user)
    await msg.answer(f"💰 Balance: <b>৳{float(u.balance or 0):.2f} BDT</b>")


@dp.message(F.text == "📊 Status")
async def on_status(msg: Message):
    u = await ensure_user(msg.from_user)
    async with SessionLocal() as s:
        rows = (await s.execute(select(Number).where(Number.assigned_user_id == u.id))).scalars().all()
    if not rows:
        await msg.answer("📭 You have no assigned numbers yet.\nTap 🤖 <b>Get Number</b> to begin.")
        return
    lines = ["📊 <b>Your active numbers:</b>\n"]
    for n in rows:
        otp_part = f"  ➜ OTP: <code>{n.last_otp}</code>" if n.last_otp else "  ⏳ Waiting…"
        country_label = f"{n.country.flag} {n.country.name}" if n.country else ""
        service_label = f"{n.service.emoji} {n.service.name}" if n.service else ""
        lines.append(f"{flag_html(n.country)} {emoji_html(n.service)} <code>+{n.phone}</code>  ·  {country_label} {service_label}\n{otp_part}\n")
    await msg.answer("\n".join(lines))


@dp.message(F.text == "🌍 Available Country")
async def on_countries(msg: Message):
    from sqlalchemy import func
    async with SessionLocal() as s:
        # only countries that currently have at least one unassigned, enabled number
        stmt = (
            select(Country, func.count(Number.id))
            .join(Number, Number.country_id == Country.id)
            .where(
                Country.enabled == True,
                Number.enabled == True,
                Number.assigned_user_id.is_(None),
            )
            .group_by(Country.id)
            .order_by(Country.name)
        )
        rows = (await s.execute(stmt)).all()
    if not rows:
        await msg.answer("📭 No countries with available numbers right now.")
        return
    text = "🌍 <b>Available countries:</b>\n\n" + "\n".join(
        f"{flag_html(c)} <b>{c.name}</b> (+{c.code}) — {cnt} available" for c, cnt in rows
    )
    await msg.answer(text)


# --------- Get Number flow ---------

@dp.message(F.text == "🤖 Get Number")
async def on_get_number(msg: Message):
    u = await ensure_user(msg.from_user)
    if u.is_banned:
        return
    async with SessionLocal() as s:
        services = (await s.execute(select(Service).where(Service.enabled == True).order_by(Service.sort_order, Service.id))).scalars().all()
    if not services:
        await msg.answer("No services available right now.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[svc_button(sv)] for sv in services])
    await msg.answer("🗝 <b>Select a Service:</b>", reply_markup=kb)


@dp.callback_query(F.data.startswith("svc:"))
async def on_service_chosen(cb: CallbackQuery):
    svc_id = int(cb.data.split(":")[1])
    async with SessionLocal() as s:
        # All available numbers for this service, with their range (if any)
        rows = (await s.execute(
            select(Country, Number, CountryRange)
            .join(Number, Number.country_id == Country.id)
            .outerjoin(CountryRange, CountryRange.id == Number.range_id)
            .where(Number.service_id == svc_id, Number.enabled == True, Number.assigned_user_id.is_(None))
        )).all()
        if not rows:
            await cb.message.edit_text("😕 No numbers available for this service. Try again later.")
            await cb.answer()
            return
        # Group by (country_id, range_id) — each range becomes its own entry
        # key: (country_id, range_id or 0) -> (Country, CountryRange|None, count)
        groups: dict[tuple[int, int], tuple[Country, "CountryRange|None", int]] = {}
        for c, _n, r in rows:
            # Skip groups whose range is disabled
            if r is not None and not r.enabled:
                continue
            key = (c.id, r.id if r else 0)
            cur = groups.get(key)
            if cur is None:
                groups[key] = (c, r, 1)
            else:
                groups[key] = (cur[0], cur[1], cur[2] + 1)
        if not groups:
            await cb.message.edit_text("😕 No numbers available for this service. Try again later.")
            await cb.answer()
            return
        sv = (await s.execute(select(Service).where(Service.id == svc_id))).scalar_one()
    # Sort: by country, then range sort_order/id; un-ranged first within a country
    def sort_key(item):
        (cid, rid), (c, r, cnt) = item
        return (-cnt, c.name.lower(), 0 if r is None else 1, (r.sort_order if r else 0), rid)
    ordered = sorted(groups.items(), key=sort_key)
    buttons = []
    lines = []
    for (cid, rid), (c, r, cnt) in ordered:
        if r is None:
            label = f"{c.flag} {c.name} (+{c.code}) - {cnt}"
            cb_data = f"ctry:{svc_id}:{cid}"
            line = f"{flag_html(c)} <b>{c.name}</b> (+{c.code}) - {cnt}"
        else:
            label = f"{c.flag} {c.name} {r.name} (+{c.code}) - {cnt}"
            cb_data = f"rng:{svc_id}:{cid}:{rid}"
            line = f"{flag_html(c)} <b>{c.name} {r.name}</b> (+{c.code}) - {cnt}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=cb_data)])
        lines.append(line)
    buttons.append([InlineKeyboardButton(text="⬅️ Back To Services", callback_data="back:svc")])
    await cb.message.edit_text(
        f"{emoji_html(sv)} <b>Select country for {sv.name}:</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await cb.answer()


@dp.callback_query(F.data == "back:svc")
async def back_to_services(cb: CallbackQuery):
    async with SessionLocal() as s:
        services = (await s.execute(select(Service).where(Service.enabled == True).order_by(Service.sort_order, Service.id))).scalars().all()
    kb = InlineKeyboardMarkup(inline_keyboard=[[svc_button(sv)] for sv in services])
    await cb.message.edit_text("🗝 <b>Select a Service:</b>", reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data.startswith("ctry:"))
async def on_country_chosen(cb: CallbackQuery):
    _, svc_id_s, ctry_id_s = cb.data.split(":")
    svc_id, ctry_id = int(svc_id_s), int(ctry_id_s)
    u = await ensure_user(cb.from_user)
    async with SessionLocal() as s:
        # Assign un-ranged numbers (ranges are now picked directly from the country list)
        avail = (await s.execute(
            select(Number).where(
                Number.service_id == svc_id,
                Number.country_id == ctry_id,
                Number.range_id.is_(None),
                Number.enabled == True,
                Number.assigned_user_id.is_(None),
            ).limit(5)
        )).scalars().all()
        if not avail:
            await cb.message.edit_text("😕 No more numbers in this country. Tap 🌍 Change Country.")
            await cb.answer()
            return
        for n in avail:
            n.assigned_user_id = u.id
            n.assigned_at = datetime.utcnow()
        await s.commit()
        sv = (await s.execute(select(Service).where(Service.id == svc_id))).scalar_one()
        ctry = (await s.execute(select(Country).where(Country.id == ctry_id))).scalar_one()
    await render_user_numbers(cb.message, u.id, svc_id, ctry_id, sv, ctry, edit=True, range_id=None)
    await cb.answer()


@dp.callback_query(F.data.startswith("rng:"))
async def on_range_chosen(cb: CallbackQuery):
    _, svc_id_s, ctry_id_s, rng_id_s = cb.data.split(":")
    svc_id, ctry_id, rng_id = int(svc_id_s), int(ctry_id_s), int(rng_id_s)
    u = await ensure_user(cb.from_user)
    async with SessionLocal() as s:
        avail = (await s.execute(
            select(Number).where(
                Number.service_id == svc_id,
                Number.country_id == ctry_id,
                Number.range_id == rng_id,
                Number.enabled == True,
                Number.assigned_user_id.is_(None),
            ).limit(5)
        )).scalars().all()
        if not avail:
            await cb.message.edit_text("😕 No more numbers in this range. Pick another.")
            await cb.answer()
            return
        for n in avail:
            n.assigned_user_id = u.id
            n.assigned_at = datetime.utcnow()
        await s.commit()
        sv = (await s.execute(select(Service).where(Service.id == svc_id))).scalar_one()
        ctry = (await s.execute(select(Country).where(Country.id == ctry_id))).scalar_one()
    await render_user_numbers(cb.message, u.id, svc_id, ctry_id, sv, ctry, edit=True, range_id=rng_id)
    await cb.answer()


async def render_user_numbers(target: Message, user_pk: int, svc_id: int, ctry_id: int, sv: Service, ctry: Country, edit: bool, range_id: int | None = None):
    async with SessionLocal() as s:
        stmt = select(Number).where(
            Number.assigned_user_id == user_pk,
            Number.service_id == svc_id,
            Number.country_id == ctry_id,
        )
        if range_id is not None:
            stmt = stmt.where(Number.range_id == range_id)
        nums = (await s.execute(stmt.limit(5))).scalars().all()
        rng_label = ""
        if range_id is not None:
            rng = (await s.execute(select(CountryRange).where(CountryRange.id == range_id))).scalar_one_or_none()
            if rng:
                rng_label = f" — {rng.name}"

    header = f"{flag_html(ctry)} {emoji_html(sv)} <b>{ctry.name}{rng_label} Number:</b>\n⏳ Waiting for OTP…\n"
    rows: list[list[InlineKeyboardButton]] = []
    for n in nums:
        if n.last_otp:
            label = f"{ctry.flag} {sv.emoji}  +{n.phone}  ➜  {n.last_otp}"
            copy = f"+{n.phone}|{n.last_otp}"
        else:
            label = f"{ctry.flag} {sv.emoji}  +{n.phone}"
            copy = f"+{n.phone}"
        rows.append([copy_button(label, copy)])
    rng_suffix = f":{range_id}" if range_id is not None else ":0"
    rows.append([InlineKeyboardButton(text="🔄 Change Number", callback_data=f"chg:{svc_id}:{ctry_id}{rng_suffix}")])
    rows.append([InlineKeyboardButton(text="🌍 Change Country", callback_data=f"svc:{svc_id}")])
    rows.append([InlineKeyboardButton(text="🔑 Get OTP", callback_data=f"refresh:{svc_id}:{ctry_id}{rng_suffix}")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    if edit:
        try:
            await target.edit_text(header, reply_markup=kb)
        except Exception:
            await target.answer(header, reply_markup=kb)
    else:
        await target.answer(header, reply_markup=kb)


def _parse_svc_ctry_rng(data: str) -> tuple[int, int, int | None]:
    parts = data.split(":")
    # parts: [tag, svc_id, ctry_id] or [tag, svc_id, ctry_id, rng_id]
    svc_id = int(parts[1]); ctry_id = int(parts[2])
    rng_id: int | None = None
    if len(parts) >= 4 and parts[3] not in ("", "0"):
        rng_id = int(parts[3])
    return svc_id, ctry_id, rng_id


@dp.callback_query(F.data.startswith("refresh:"))
async def on_refresh(cb: CallbackQuery):
    svc_id, ctry_id, rng_id = _parse_svc_ctry_rng(cb.data)
    u = await ensure_user(cb.from_user)
    async with SessionLocal() as s:
        sv = (await s.execute(select(Service).where(Service.id == svc_id))).scalar_one()
        ctry = (await s.execute(select(Country).where(Country.id == ctry_id))).scalar_one()
    await render_user_numbers(cb.message, u.id, svc_id, ctry_id, sv, ctry, edit=True, range_id=rng_id)
    await cb.answer("Refreshed")


@dp.callback_query(F.data.startswith("chg:"))
async def on_change_number(cb: CallbackQuery):
    svc_id, ctry_id, rng_id = _parse_svc_ctry_rng(cb.data)
    u = await ensure_user(cb.from_user)
    async with SessionLocal() as s:
        # release current numbers without OTP and assign new ones (within range if applicable)
        cur_stmt = select(Number).where(
            Number.assigned_user_id == u.id,
            Number.service_id == svc_id,
            Number.country_id == ctry_id,
            Number.last_otp.is_(None),
        )
        if rng_id is not None:
            cur_stmt = cur_stmt.where(Number.range_id == rng_id)
        current = (await s.execute(cur_stmt)).scalars().all()
        for n in current:
            n.assigned_user_id = None
            n.assigned_at = None
        await s.flush()
        av_stmt = select(Number).where(
            Number.service_id == svc_id,
            Number.country_id == ctry_id,
            Number.enabled == True,
            Number.assigned_user_id.is_(None),
        )
        if rng_id is not None:
            av_stmt = av_stmt.where(Number.range_id == rng_id)
        avail = (await s.execute(av_stmt.limit(5))).scalars().all()
        for n in avail:
            n.assigned_user_id = u.id
            n.assigned_at = datetime.utcnow()
        await s.commit()
        sv = (await s.execute(select(Service).where(Service.id == svc_id))).scalar_one()
        ctry = (await s.execute(select(Country).where(Country.id == ctry_id))).scalar_one()
    await render_user_numbers(cb.message, u.id, svc_id, ctry_id, sv, ctry, edit=True, range_id=rng_id)
    await cb.answer("New numbers assigned")


# ============= OTP feed listener =============

def _extract_copy_texts(message: Message) -> list[str]:
    out: list[str] = []
    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row in message.reply_markup.inline_keyboard:
            for btn in row:
                # aiogram 3 uses .copy_text attribute (CopyTextButton)
                ct = getattr(btn, "copy_text", None)
                if ct is not None:
                    txt = getattr(ct, "text", None) or (ct.get("text") if isinstance(ct, dict) else None)
                    if txt:
                        out.append(txt)
    return out


@dp.channel_post()
@dp.edited_channel_post()
async def on_feed_post(msg: Message):
    if not settings.OTP_FEED_CHANNEL_ID or msg.chat.id != settings.OTP_FEED_CHANNEL_ID:
        return
    text = (msg.text or msg.caption or "")
    copy_texts = _extract_copy_texts(msg)
    parsed = parse_message(text, copy_texts)
    if not parsed:
        log.info("Feed message ignored (no parse): %s", text[:80])
        return

    log.info("Parsed OTP phone=%s code=%s service=%s", parsed.phone, parsed.code, parsed.service_hint)

    async with SessionLocal() as s:
        # find a number matching the phone (and optionally service)
        stmt = select(Number).where(Number.phone == parsed.phone, Number.assigned_user_id.is_not(None))
        match = (await s.execute(stmt)).scalars().first()
        otp_row = Otp(
            phone=parsed.phone,
            code=parsed.code,
            raw_text=text[:1000],
            service_hint=parsed.service_hint,
        )
        svc = None
        ctry = None
        if match:
            match.last_otp = parsed.code
            match.last_otp_at = datetime.utcnow()
            otp_row.matched_number_id = match.id
            otp_row.delivered_to_user_id = match.assigned_user_id
            user = (await s.execute(select(TgUser).where(TgUser.id == match.assigned_user_id))).scalar_one_or_none()
            svc = (await s.execute(select(Service).where(Service.id == match.service_id))).scalar_one_or_none()
            ctry = (await s.execute(select(Country).where(Country.id == match.country_id))).scalar_one_or_none()
        else:
            user = None
        s.add(otp_row)
        await s.commit()

        # forward to user — premium emoji + premium buttons via raw Bot API
        if match and user and not user.is_banned:
            from .delivery import send_otp_message
            ok = await send_otp_message(
                user.tg_id,
                phone=match.phone,
                code=parsed.code,
                service=svc,
                country=ctry,
            )
            if not ok:
                log.warning("Feed: failed to deliver OTP to %s", user.tg_id)


# ============= Entrypoint =============

# ============= Entrypoint =============

async def main():
    global bot
    if not settings.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is required — set it in your .env file")
    await init_db()
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Sanity check + clear any stale webhook (most common cause of "/start gives no reply")
    try:
        me = await bot.get_me()
        log.info("Bot identity: @%s id=%s name=%r", me.username, me.id, me.first_name)
    except Exception as e:
        raise SystemExit(f"BOT_TOKEN is invalid (getMe failed): {e}")

    try:
        info = await bot.get_webhook_info()
        if info.url:
            log.warning("Found existing webhook %r — deleting so polling can receive updates", info.url)
        # Always delete + drop any queued updates from prior bad runs.
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Webhook cleared, pending updates dropped.")
    except Exception as e:
        log.warning("delete_webhook failed (continuing anyway): %s", e)

    log.info("Starting bot. Brand=%s Feed=%s", settings.BOT_BRAND_NAME, settings.OTP_FEED_CHANNEL_ID)
    # background worker for IPRN/other providers
    asyncio.create_task(ims_main(bot))
    # Explicit update list so private chats (`message`) AND channel feed both work.
    await dp.start_polling(
        bot,
        allowed_updates=["message", "edited_message", "callback_query",
                         "channel_post", "edited_channel_post"],
    )


@dp.message(F.web_app_data)
async def on_web_app_data(msg: Message):
    """Receive service+country selection from the Mini App (premium-icon menu)."""
    import json
    try:
        payload = json.loads(msg.web_app_data.data)
        svc_id = int(payload["service_id"]); ctry_id = int(payload["country_id"])
    except Exception:
        await msg.answer("⚠️ Invalid selection from Mini App.")
        return
    u = await ensure_user(msg.from_user)
    async with SessionLocal() as s:
        avail = (await s.execute(
            select(Number).where(
                Number.service_id == svc_id, Number.country_id == ctry_id,
                Number.enabled == True, Number.assigned_user_id.is_(None),
            ).limit(5)
        )).scalars().all()
        if not avail:
            await msg.answer("😕 No more numbers in this country.")
            return
        for n in avail:
            n.assigned_user_id = u.id
            n.assigned_at = datetime.utcnow()
        await s.commit()
        sv = (await s.execute(select(Service).where(Service.id == svc_id))).scalar_one()
        ctry = (await s.execute(select(Country).where(Country.id == ctry_id))).scalar_one()
    await render_user_numbers(msg, u.id, svc_id, ctry_id, sv, ctry, edit=False)


if __name__ == "__main__":
    asyncio.run(main())
