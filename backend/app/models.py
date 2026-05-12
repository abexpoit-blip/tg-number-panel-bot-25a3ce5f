from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    keyword: Mapped[str] = mapped_column(String(80), index=True)
    emoji: Mapped[str] = mapped_column(String(16), default="📱")
    custom_emoji_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Telegram premium emoji
    icon_mode: Mapped[str] = mapped_column(String(16), default="auto")  # auto | custom | brand | default
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Country(Base):
    __tablename__ = "countries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(8), index=True)
    iso: Mapped[str] = mapped_column(String(4), default="")
    flag: Mapped[str] = mapped_column(String(16), default="🌍")
    custom_emoji_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Telegram premium flag emoji
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class CountryRange(Base):
    """Sub-range of a country (e.g. 'Peru 1' covering numbers starting with 5198).

    Bot shows ranges as a sub-step after the user picks the country, so a single
    country can expose multiple labelled buckets.
    """
    __tablename__ = "country_ranges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))               # e.g. "Peru 1"
    prefix: Mapped[str] = mapped_column(String(32), default="")  # informational, e.g. "5198"
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    country: Mapped[Country] = relationship(lazy="joined")


class TgUser(Base):
    __tablename__ = "tg_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Provider(Base):
    """External SMS/OTP provider account (e.g. iprn-sms, seven1tel, etc.)."""
    __tablename__ = "providers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)            # human label
    type: Mapped[str] = mapped_column(String(32), default="iprn", index=True)  # iprn|seven1tel|...
    base_url: Mapped[str] = mapped_column(String(255), default="https://panel.iprn-sms.com")
    username: Mapped[str] = mapped_column(String(120))
    password: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(8), default="EUR")       # EUR|USD|GBP
    cookies_json: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_interval: Mapped[int] = mapped_column(Integer, default=15)        # seconds
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Number(Base):
    __tablename__ = "numbers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"), nullable=True, index=True)
    range_id: Mapped[int | None] = mapped_column(ForeignKey("country_ranges.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("tg_users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_otp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_otp_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    service: Mapped[Service] = relationship(lazy="joined")
    country: Mapped[Country] = relationship(lazy="joined")
    provider: Mapped["Provider | None"] = relationship(lazy="joined")
    range_: Mapped["CountryRange | None"] = relationship(lazy="joined", foreign_keys=[range_id])

    # Uniqueness is enforced at the DB level via partial indexes (see main.py
    # _ensure_columns) so the same phone+service can exist in different ranges.


class Otp(Base):
    __tablename__ = "otps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str] = mapped_column(String(32))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    service_hint: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"), nullable=True, index=True)
    delivered_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("tg_users.id", ondelete="SET NULL"), nullable=True, index=True)
    matched_number_id: Mapped[int | None] = mapped_column(ForeignKey("numbers.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
