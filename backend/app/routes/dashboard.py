from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..db import get_db
from ..models import Country, CountryRange, Number, Otp, Service, TgUser

router = APIRouter()


@router.get("/dashboard")
async def dashboard(_: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    total_numbers = (await db.execute(select(func.count(Number.id)))).scalar_one()
    assigned_numbers = (await db.execute(select(func.count(Number.id)).where(Number.assigned_user_id.is_not(None)))).scalar_one()
    total_users = (await db.execute(select(func.count(TgUser.id)))).scalar_one()
    total_otps = (await db.execute(select(func.count(Otp.id)))).scalar_one()
    today = datetime.utcnow() - timedelta(hours=24)
    otps_24h = (await db.execute(select(func.count(Otp.id)).where(Otp.created_at >= today))).scalar_one()
    return {
        "total_numbers": total_numbers,
        "assigned_numbers": assigned_numbers,
        "available_numbers": total_numbers - assigned_numbers,
        "total_users": total_users,
        "total_otps": total_otps,
        "otps_24h": otps_24h,
    }


@router.get("/dashboard/charts")
async def dashboard_charts(_: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    """Hourly OTP buckets for the last 24h + top 5 services in 7d + top 5 countries in 7d."""
    now = datetime.utcnow()

    # --- Hourly OTPs last 24h ---
    since_24h = now - timedelta(hours=24)
    rows_24h = (await db.execute(
        select(Otp.created_at).where(Otp.created_at >= since_24h)
    )).scalars().all()
    buckets: dict[str, int] = {}
    for h in range(24, -1, -1):
        ts = (now - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        buckets[ts.strftime("%H:00")] = 0
    for ts in rows_24h:
        key = ts.replace(minute=0, second=0, microsecond=0).strftime("%H:00")
        if key in buckets:
            buckets[key] += 1
    hourly = [{"hour": k, "count": v} for k, v in buckets.items()]

    # --- Top 5 services last 7d (by OTPs delivered to assigned numbers of that service) ---
    since_7d = now - timedelta(days=7)
    top_services_q = (await db.execute(
        select(Service.name, Service.emoji, func.count(Otp.id))
        .join(Number, Number.id == Otp.matched_number_id)
        .join(Service, Service.id == Number.service_id)
        .where(Otp.created_at >= since_7d)
        .group_by(Service.id)
        .order_by(func.count(Otp.id).desc())
        .limit(5)
    )).all()
    top_services = [{"name": n, "emoji": e or "📱", "count": c} for n, e, c in top_services_q]

    # --- 7-day daily trend ---
    daily_rows = (await db.execute(
        select(Otp.created_at).where(Otp.created_at >= since_7d)
    )).scalars().all()
    daily: dict[str, int] = {}
    for d in range(7, -1, -1):
        key = (now - timedelta(days=d)).strftime("%a %d")
        daily[key] = 0
    for ts in daily_rows:
        key = ts.strftime("%a %d")
        if key in daily:
            daily[key] += 1
    daily_list = [{"day": k, "count": v} for k, v in daily.items()]

    return {"hourly": hourly, "daily": daily_list, "top_services": top_services}
