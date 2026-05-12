"""OTP delivery via raw Telegram Bot API.

aiogram 3.15 doesn't model the newest InlineKeyboardButton fields
(`icon_custom_emoji_id`, `style`, `copy_text` together).  Telegram added
these so premium-emoji-capable bots can render exactly the same look as
the IMS Panel reference message.

Sending the OTP message via raw HTTPS lets us pass those fields verbatim.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .config import settings
from .db import Country, Service, get_setting
from .emoji import flag_emoji_html, service_emoji_html

log = logging.getLogger("bot.delivery")

API_BASE = "https://api.telegram.org"


async def _build_keyboard(code: str, service: Service | None = None) -> list[list[dict[str, Any]]]:
    """IMS-Panel-style 2-row keyboard.

    Row 1: copy-OTP button (primary). Icon = service's custom emoji if set,
           else falls back to the global `otp_button_emoji_id` setting.
    Row 2: Main Channel (danger) + Number Channel (success).
    """
    # Prefer the service's own premium emoji so the OTP button matches the service.
    svc_icon = (getattr(service, "custom_emoji_id", None) or "").strip() if service else ""
    fallback_icon = await get_setting("otp_button_emoji_id", "")
    otp_icon = svc_icon or fallback_icon
    main_url = await get_setting("main_channel_url", "")
    num_url = await get_setting("number_channel_url", "")
    main_icon = await get_setting("main_channel_emoji_id", "")
    num_icon = await get_setting("number_channel_emoji_id", "")

    row1: dict[str, Any] = {
        "text": code,
        "style": "primary",
        "copy_text": {"text": code},
    }
    if otp_icon:
        row1["icon_custom_emoji_id"] = otp_icon

    rows: list[list[dict[str, Any]]] = [[row1]]

    bottom: list[dict[str, Any]] = []
    if main_url:
        b = {"text": "Main Channel", "style": "danger", "url": main_url}
        if main_icon:
            b["icon_custom_emoji_id"] = main_icon
        bottom.append(b)
    if num_url:
        b = {"text": "Number Channel", "style": "success", "url": num_url}
        if num_icon:
            b["icon_custom_emoji_id"] = num_icon
        bottom.append(b)
    if bottom:
        rows.append(bottom)

    return rows



async def send_otp_message(
    chat_id: int,
    *,
    phone: str,
    code: str,
    service: Service | None,
    country: Country | None,
) -> bool:
    """Send the OTP message via raw Bot API. Returns True on success."""
    if not settings.BOT_TOKEN:
        log.error("BOT_TOKEN not configured; cannot deliver OTP")
        return False

    flag = flag_emoji_html(country)
    emoji = service_emoji_html(service)
    iso = (country.iso or "").upper() if country else ""
    hashtag = f" #{iso}" if iso else ""

    text = (
        f"{flag}{hashtag} {emoji} <code>{phone}</code>"
    )

    keyboard = await _build_keyboard(code, service)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": keyboard},
    }

    url = f"{API_BASE}/bot{settings.BOT_TOKEN}/sendMessage"
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.post(url, json=payload) as r:
                data = await r.json(content_type=None)
                if not data.get("ok"):
                    log.warning("sendMessage failed for chat=%s: %s", chat_id, data)
                    # Fallback: retry without premium fields if Telegram rejected them
                    if any(k in str(data) for k in ("icon_custom_emoji_id", "style", "BUTTON_INVALID")):
                        return await _send_fallback(sess, chat_id, text, code)
                    return False
                return True
    except Exception as e:
        log.exception("Raw sendMessage error to %s: %s", chat_id, e)
        return False


async def _send_fallback(sess: aiohttp.ClientSession, chat_id: int, text: str, code: str) -> bool:
    """Fallback: drop premium-only fields the bot isn't allowed to use."""
    main_url = await get_setting("main_channel_url", "")
    num_url = await get_setting("number_channel_url", "")
    rows: list[list[dict[str, Any]]] = [[{"text": f"📋 {code}", "copy_text": {"text": code}}]]
    bottom = []
    if main_url:
        bottom.append({"text": "Main Channel", "url": main_url})
    if num_url:
        bottom.append({"text": "Number Channel", "url": num_url})
    if bottom:
        rows.append(bottom)
    payload = {
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": rows},
    }
    url = f"{API_BASE}/bot{settings.BOT_TOKEN}/sendMessage"
    async with sess.post(url, json=payload) as r:
        data = await r.json(content_type=None)
        if not data.get("ok"):
            log.error("Fallback sendMessage also failed: %s", data)
            return False
        return True
