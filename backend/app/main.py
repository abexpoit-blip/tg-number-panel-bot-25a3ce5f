from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .auth import hash_pw, verify_pw
from .config import settings
from .db import Base, SessionLocal, engine
from .models import Admin, Country, Provider, Service
from .routes import auth as auth_routes
from .routes import countries, dashboard, ims, numbers, providers as providers_routes, services, settings as settings_routes, sms, users, withdrawals


async def _ensure_columns(conn):
    """Add columns introduced after first deploy (idempotent)."""
    stmts = [
        "ALTER TABLE services  ADD COLUMN IF NOT EXISTS custom_emoji_id VARCHAR(64)",
        "ALTER TABLE services  ADD COLUMN IF NOT EXISTS icon_mode VARCHAR(16) DEFAULT 'auto'",
        "ALTER TABLE countries ADD COLUMN IF NOT EXISTS custom_emoji_id VARCHAR(64)",
        "ALTER TABLE numbers  ADD COLUMN IF NOT EXISTS provider_id INTEGER REFERENCES providers(id) ON DELETE SET NULL",
        "ALTER TABLE otps     ADD COLUMN IF NOT EXISTS provider_id INTEGER REFERENCES providers(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS ix_numbers_provider_id ON numbers(provider_id)",
        "CREATE INDEX IF NOT EXISTS ix_otps_provider_id ON otps(provider_id)",
    ]
    from sqlalchemy import text
    for s in stmts:
        try:
            await conn.execute(text(s))
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_columns(conn)
    async with SessionLocal() as s:
        # Keep exactly one usable admin synced with the current environment values.
        admins = (await s.execute(select(Admin).order_by(Admin.id))).scalars().all()
        primary = next((admin for admin in admins if admin.email == settings.ADMIN_EMAIL), None) or (admins[0] if admins else None)
        if primary:
            primary.email = settings.ADMIN_EMAIL
            if settings.ADMIN_PASSWORD and not verify_pw(settings.ADMIN_PASSWORD, primary.password_hash):
                primary.password_hash = hash_pw(settings.ADMIN_PASSWORD)
        else:
            s.add(Admin(email=settings.ADMIN_EMAIL, password_hash=hash_pw(settings.ADMIN_PASSWORD)))
        # seed default services
        if not (await s.execute(select(Service))).first():
            defaults = [
                ("WhatsApp", "WHATSAPP", "🟢", 1),
                ("Facebook 1", "FACEBOOK", "📘", 2),
                ("Facebook 2", "FACEBOOK", "📘", 3),
                ("Instagram", "INSTAGRAM", "📷", 4),
                ("Telegram", "TELEGRAM", "✈️", 5),
                ("WhatsApp 2", "WHATSAPP", "🟢", 6),
                ("TikTok", "TIKTOK", "🎵", 7),
            ]
            for name, kw, emoji, order in defaults:
                s.add(Service(name=name, keyword=kw, emoji=emoji, sort_order=order))
        # seed common countries
        if not (await s.execute(select(Country))).first():
            ctry = [
                ("Germany", "49", "DE", "🇩🇪"),
                ("Senegal", "221", "SN", "🇸🇳"),
                ("Tanzania", "255", "TZ", "🇹🇿"),
                ("Burundi", "257", "BI", "🇧🇮"),
                ("Timor", "670", "TL", "🇹🇱"),
                ("Uzbekistan", "998", "UZ", "🇺🇿"),
                ("Philippines", "63", "PH", "🇵🇭"),
                ("Myanmar", "95", "MM", "🇲🇲"),
                ("Venezuela", "58", "VE", "🇻🇪"),
            ]
            for name, code, iso, flag in ctry:
                s.add(Country(name=name, code=code, iso=iso, flag=flag))
        # seed IMS provider rows so admins can wire numbers to a specific IMS slot
        existing_providers = {p.name for p in (await s.execute(select(Provider))).scalars().all()}
        for slot_name in ("IMS #1", "IMS #2"):
            if slot_name not in existing_providers:
                s.add(Provider(
                    name=slot_name,
                    type="ims",
                    base_url="https://www.imssms.org",
                    username="",
                    password="",
                    currency="EUR",
                    enabled=True,
                ))
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
            existing = (await s.execute(select(Admin).where(Admin.email == settings.ADMIN_EMAIL))).scalar_one_or_none()
            if existing and settings.ADMIN_PASSWORD:
                existing.password_hash = hash_pw(settings.ADMIN_PASSWORD)
                await s.commit()
    yield


app = FastAPI(title="Seven1tel Panel API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(services.router, prefix="/services", tags=["services"])
app.include_router(countries.router, prefix="/countries", tags=["countries"])
app.include_router(numbers.router, prefix="/numbers", tags=["numbers"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(withdrawals.router, prefix="/withdrawals", tags=["withdrawals"])
app.include_router(sms.router, prefix="/sms", tags=["sms"])
app.include_router(settings_routes.router, prefix="/settings", tags=["settings"])
app.include_router(ims.router, prefix="/ims", tags=["ims"])
app.include_router(providers_routes.router, prefix="/providers", tags=["providers"])


@app.get("/health")
async def health():
    return {"ok": True}
