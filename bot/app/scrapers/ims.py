"""IMS-SMS scraper — Python port of imsBot.js.

Login:   POST /signin with { etkk (hidden), username, password, capt (math) }
CDR:     GET /client/res/data_smscdr.php?...&sesskey=<from page>
         DataTables JSON: aaData = [[datetime, range, number, cli, msg,
         currency, payout], ...]

IMPORTANT — IMS rate limit: portal warns "Don't refresh CDR & stats page
frequently within 15 seconds". Violation returns 503. Hard floor 16s.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import aiohttp

log = logging.getLogger("scraper.ims")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0 Safari/537.36")

MIN_INTERVAL_FLOOR = 16          # IMS rule = 15s, +1s safety
DEFAULT_INTERVAL = 18
DEFAULT_PENALTY_BASE = 60
DEFAULT_PENALTY_MAX = 600
DEFAULT_PENALTY_STEPS = 6


class ImsRateLimited(RuntimeError):
    pass


class ImsSessionLost(RuntimeError):
    pass


class ImsLoginError(RuntimeError):
    pass


@dataclass
class ImsRow:
    datetime: str
    range: str
    phone: str
    cli: str
    message: str
    cdr_at: int | None = None

    def extract_code(self) -> str | None:
        # Match digit run with word boundaries (don't strip whitespace).
        m = re.search(r"\b(\d{4,8})\b", self.message)
        if m:
            return m.group(1)
        # Fallback: collapse "458-825" → "458825"
        collapsed = re.sub(r"(?<=\d)[\-.](?=\d)", "", self.message)
        m = re.search(r"\b(\d{4,8})\b", collapsed)
        return m.group(1) if m else None

    def dedup_key(self) -> str:
        return f"{self.datetime}|{self.phone}|{self.message[:60]}"


def _solve_captcha(html: str) -> str | None:
    m = re.search(r"What\s+is\s+(\d+)\s*([+\-x*/])\s*(\d+)", html, re.I)
    if not m:
        return None
    a, op, b = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    if op == "+":
        return str(a + b)
    if op == "-":
        return str(a - b)
    if op in ("*", "x"):
        return str(a * b)
    if op == "/":
        return str(a // b)
    return None


def _parse_panel_ts(date_col: str) -> int | None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}):(\d{2}))?", date_col or "")
    if not m or not m.group(4):
        return None
    try:
        return int(datetime(*(int(g) for g in m.groups())).timestamp())  # type: ignore[arg-type]
    except Exception:
        return None


@dataclass
class ImsClient:
    base_url: str = "https://www.imssms.org"
    username: str = ""
    password: str = ""
    session_cookie: str = ""              # "PHPSESSID=...; Path=/" persisted PHPSESSID
    cookie_header: str = ""               # optional manual override (skips captcha)
    interval: int = DEFAULT_INTERVAL
    label: str = "ims"
    # state
    _jar: aiohttp.CookieJar = field(default_factory=lambda: aiohttp.CookieJar(unsafe=True))
    _sesskey: str | None = None
    _logged_in: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _next_allowed_at: float = 0.0
    _rl_streak: int = 0
    _last_success_at: float | None = None
    _last_error: str | None = None

    def __post_init__(self) -> None:
        self.base_url = (self.base_url or "https://www.imssms.org").rstrip("/")
        if self.interval < MIN_INTERVAL_FLOOR:
            self.interval = MIN_INTERVAL_FLOOR
        self._load_cookies()

    # -------- cookie helpers --------
    def _load_cookies(self) -> None:
        from yarl import URL
        from http.cookies import SimpleCookie
        url = URL(self.base_url)
        raw = (self.cookie_header or self.session_cookie or "").strip()
        if not raw:
            return
        sc = SimpleCookie()
        try:
            sc.load(raw)
        except Exception:
            log.warning("[%s] cookie parse failed", self.label)
            return
        self._jar.update_cookies({k: v.value for k, v in sc.items()}, response_url=url)

    def current_session_cookie(self) -> str:
        """Return PHPSESSID=value cookie string for persistence."""
        from yarl import URL
        url = URL(self.base_url)
        for c in self._jar.filter_cookies(url).values():
            if c.key.upper() == "PHPSESSID":
                return f"{c.key}={c.value}"
        return ""

    # -------- HTTP --------
    def _session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            cookie_jar=self._jar,
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=aiohttp.ClientTimeout(total=25),
        )

    # -------- rate limiting --------
    async def _gate(self) -> None:
        async with self._lock:
            now = time.time()
            wait = self._next_allowed_at - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_allowed_at = time.time() + max(MIN_INTERVAL_FLOOR, self.interval)

    def _register_penalty(self) -> int:
        self._rl_streak += 1
        step = min(self._rl_streak, DEFAULT_PENALTY_STEPS)
        penalty = min(DEFAULT_PENALTY_MAX, DEFAULT_PENALTY_BASE * step)
        self._next_allowed_at = max(self._next_allowed_at, time.time() + penalty)
        log.warning("[%s] IMS rate-limit cooldown %ss (streak=%d)", self.label, penalty, self._rl_streak)
        return penalty

    # -------- login / sesskey --------
    async def _refresh_sesskey(self, sess: aiohttp.ClientSession) -> str:
        async with sess.get(f"{self.base_url}/client/SMSCDRStats", allow_redirects=True) as r:
            if r.status in (429, 503):
                raise ImsRateLimited("cdr_rate_limited")
            if r.status != 200:
                raise RuntimeError(f"cdr_page_{r.status}")
            html = await r.text()
        if re.search(r"15\s*second|within\s+\d+\s*sec|refresh\s+.*frequent|too\s+many", html, re.I):
            raise ImsRateLimited("cdr_rate_limited")
        if re.search(r"<form[^>]+action=['\"]?signin", html, re.I):
            self._logged_in = False
            raise ImsSessionLost("cdr_session_lost")
        m = re.search(r"data_smscdr\.php\?[^'\"]*sesskey=([^&'\"\s]+)", html)
        if not m:
            raise RuntimeError("sesskey_not_found")
        self._sesskey = m.group(1)
        return self._sesskey

    async def login(self, force_captcha: bool = False) -> None:
        if not self.username and not self.password and not (self.cookie_header or self.session_cookie):
            raise ImsLoginError("ims_creds_missing (username/password OR cookie header required)")

        async with self._session() as sess:
            # Try saved/manual cookie first
            if not force_captcha and (self.cookie_header or self.session_cookie or self.current_session_cookie()):
                try:
                    await self._gate()
                    await self._refresh_sesskey(sess)
                    self._logged_in = True
                    log.info("[%s] cookie-resume OK (skipped captcha)", self.label)
                    return
                except ImsRateLimited:
                    raise
                except Exception as e:
                    log.info("[%s] cookie-resume failed (%s) — captcha login", self.label, e)

            if not (self.username and self.password):
                raise ImsLoginError("ims_cookie_expired (paste fresh PHPSESSID or set username/password)")

            async with sess.get(f"{self.base_url}/login", allow_redirects=True) as r:
                html = await r.text()
            etkk_m = re.search(r"name=['\"]etkk['\"]\s+value=['\"]([^'\"]+)['\"]", html)
            capt = _solve_captcha(html)
            form = aiohttp.FormData()
            if etkk_m:
                form.add_field("etkk", etkk_m.group(1))
            form.add_field("username", self.username)
            form.add_field("password", self.password)
            if capt is not None:
                form.add_field("capt", capt)
            async with sess.post(
                f"{self.base_url}/signin", data=form, allow_redirects=True,
                headers={"Referer": f"{self.base_url}/login", "Origin": self.base_url},
            ) as r:
                final = str(r.url)
                body = await r.text()
                if "/login" in final and "logout" not in body.lower():
                    raise ImsLoginError(f"signin rejected status={r.status}")
            await self._gate()
            await self._refresh_sesskey(sess)
            self._logged_in = True
            log.info("[%s] captcha login OK as %s", self.label, self.username)

    # -------- CDR fetch --------
    async def fetch_cdr_rows(self) -> list[ImsRow]:
        await self._gate()
        async with self._session() as sess:
            if not self._sesskey or not self._logged_in:
                await self._refresh_sesskey(sess)
            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)
            tomorrow = now + timedelta(days=1)
            fdate1 = yesterday.strftime("%Y-%m-%d 00:00:00")
            fdate2 = tomorrow.strftime("%Y-%m-%d 23:59:59")

            params: list[tuple[str, str]] = [
                ("fdate1", fdate1), ("fdate2", fdate2),
                ("frange", ""), ("fnum", ""), ("fcli", ""),
                ("fgdate", ""), ("fgmonth", ""), ("fgrange", ""),
                ("fgnumber", ""), ("fgcli", ""), ("fg", "0"),
                ("sesskey", self._sesskey or ""),
                ("sEcho", str(int(time.time() * 1000) % 100000)),
                ("iColumns", "7"),
                ("sColumns", ",,,,,,"),
                ("iDisplayStart", "0"),
                ("iDisplayLength", "300"),
                ("iSortCol_0", "0"),
                ("sSortDir_0", "desc"),
                ("iSortingCols", "1"),
                ("_", str(int(time.time() * 1000))),
            ]
            for i in range(7):
                params += [
                    (f"mDataProp_{i}", str(i)),
                    (f"sSearch_{i}", ""),
                    (f"bRegex_{i}", "false"),
                    (f"bSearchable_{i}", "true"),
                    (f"bSortable_{i}", "true"),
                ]
            # mimic browser delay between page render and AJAX
            await asyncio.sleep(0.4 + random.random() * 0.2)
            url = f"{self.base_url}/client/res/data_smscdr.php"
            async with sess.get(
                url, params=params,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{self.base_url}/client/SMSCDRStats",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
            ) as r:
                if r.status in (401, 403):
                    self._logged_in = False
                    raise ImsSessionLost("cdr_unauthorized")
                if r.status in (429, 503):
                    raise ImsRateLimited("cdr_rate_limited")
                if r.status >= 400:
                    raise RuntimeError(f"cdr_http_{r.status}")
                txt = await r.text()
            if not txt.strip():
                raise RuntimeError("cdr_empty_response")
            if re.search(r"<form[^>]+action=['\"]?signin", txt, re.I):
                self._logged_in = False
                raise ImsSessionLost("cdr_session_lost")
            if re.search(r"15\s*second|within\s+\d+\s*sec|refresh\s+.*frequent|too\s+many", txt, re.I):
                raise ImsRateLimited("cdr_rate_limited")
            import json as _json
            try:
                data = _json.loads(txt)
            except Exception:
                raise RuntimeError("cdr_bad_response")
            aa = data.get("aaData") if isinstance(data, dict) else None
            if not isinstance(aa, list):
                raise RuntimeError("cdr_bad_shape")

            self._last_success_at = time.time()
            self._rl_streak = 0
            self._last_error = None

            rows: list[ImsRow] = []
            for raw in aa:
                if not isinstance(raw, list) or len(raw) < 5:
                    continue
                phone = re.sub(r"\D", "", str(raw[2] or ""))
                msg = str(raw[4] or "")
                if not phone or not msg:
                    continue
                rows.append(ImsRow(
                    datetime=str(raw[0] or ""),
                    range=str(raw[1] or ""),
                    phone=phone,
                    cli=str(raw[3] or ""),
                    message=msg,
                    cdr_at=_parse_panel_ts(str(raw[0] or "")),
                ))
            return rows

    def status(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "base_url": self.base_url,
            "username": (self.username[:2] + "***") if self.username else None,
            "logged_in": self._logged_in,
            "interval_sec": self.interval,
            "min_interval_floor": MIN_INTERVAL_FLOOR,
            "rl_streak": self._rl_streak,
            "next_cdr_allowed_at": int(self._next_allowed_at) if self._next_allowed_at else None,
            "last_success_at": int(self._last_success_at) if self._last_success_at else None,
            "last_error": self._last_error,
            "sesskey_loaded": bool(self._sesskey),
        }
