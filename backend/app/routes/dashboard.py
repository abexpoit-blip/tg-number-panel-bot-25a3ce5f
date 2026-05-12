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


@router.get("/dashboard/range-stats")
async def dashboard_range_stats(_: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    """Per-(country, range) breakdown: total / assigned / available numbers.

    Each country range (Peru 1, Peru 2, ...) shows up as its own row, plus a
    pseudo-row for un-ranged numbers (range_id IS NULL) labelled just by country.
    """
    # Conditional aggregates so a single GROUP BY gives accurate per-bucket counts.
    # "available" matches the bot's definition: enabled & not yet assigned to anyone.
    # Disabled ranges are excluded from buckets entirely (their numbers also drop out).
    available_expr = func.count(Number.id).filter(
        Number.enabled == True,  # noqa: E712
        Number.assigned_user_id.is_(None),
    )
    assigned_expr = func.count(Number.id).filter(Number.assigned_user_id.is_not(None))
    disabled_expr = func.count(Number.id).filter(Number.enabled == False)  # noqa: E712

    rows = (await db.execute(
        select(
            Country.id.label("cid"),
            Country.name.label("cname"),
            Country.flag.label("cflag"),
            Country.code.label("ccode"),
            CountryRange.id.label("rid"),
            CountryRange.name.label("rname"),
            CountryRange.sort_order.label("rsort"),
            func.count(Number.id).label("total"),
            assigned_expr.label("assigned"),
            available_expr.label("available"),
            disabled_expr.label("disabled"),
        )
        .select_from(Number)
        .join(Country, Country.id == Number.country_id)
        .outerjoin(
            CountryRange,
            (CountryRange.id == Number.range_id) & (CountryRange.enabled == True),  # noqa: E712
        )
        # Drop numbers that point to a disabled range (range_id set but join missed because enabled=False)
        .where(
            (Number.range_id.is_(None)) | (CountryRange.id.is_not(None))
        )
        .group_by(Country.id, CountryRange.id, CountryRange.name, CountryRange.sort_order)
    )).all()

    out = []
    for r in rows:
        total = int(r.total or 0)
        out.append({
            "country_id": r.cid,
            "country_name": r.cname,
            "country_flag": r.cflag,
            "country_code": r.ccode,
            "range_id": r.rid,
            "range_name": r.rname,
            "label": (f"{r.cname} {r.rname}" if r.rname else r.cname),
            "total": total,
            "assigned": int(r.assigned or 0),
            "available": int(r.available or 0),
            "disabled": int(r.disabled or 0),
        })
    out.sort(key=lambda x: (
        x["country_name"].lower(),
        0 if x["range_id"] is None else 1,
        x["range_name"] or "",
    ))
    return out
