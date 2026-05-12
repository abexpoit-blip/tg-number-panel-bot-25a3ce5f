import re
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..db import get_db
from ..models import CountryRange, Number

router = APIRouter()


class NumberIn(BaseModel):
    phone: str
    service_id: int
    country_id: int
    provider_id: int | None = None
    range_id: int | None = None
    enabled: bool = True


class BulkIn(BaseModel):
    service_id: int
    country_id: int
    provider_id: int | None = None
    range_id: int | None = None
    phones: str  # newline / comma / space separated


def _assigned_filter(status: str | None) -> str | None:
    if status == "reserved":
        return "yes"
    if status == "available":
        return "no"
    return None


def _d(n: Number):
    return {
        "id": n.id,
        "phone": n.phone,
        "service_id": n.service_id,
        "country_id": n.country_id,
        "provider_id": n.provider_id,
        "range_id": n.range_id,
        "service": n.service.name if n.service else None,
        "service_name": n.service.name if n.service else None,
        "service_keyword": n.service.keyword if n.service else None,
        "country": n.country.name if n.country else None,
        "country_name": n.country.name if n.country else None,
        "provider": n.provider.name if n.provider else None,
        "range_name": n.range_.name if n.range_ else None,
        "country_flag": n.country.flag if n.country else None,
        "country_code": n.country.code if n.country else None,
        "service_emoji": n.service.emoji if n.service else None,
        "assigned_user_id": n.assigned_user_id,
        "assigned_at": n.assigned_at.isoformat() if n.assigned_at else None,
        "last_otp": n.last_otp,
        "last_otp_at": n.last_otp_at.isoformat() if n.last_otp_at else None,
        "enabled": n.enabled,
    }


def _range_match(range_id: int | None):
    return Number.range_id.is_(None) if range_id is None else Number.range_id == range_id


async def _validated_range_id(db: AsyncSession, country_id: int, range_id: int | None) -> int | None:
    range_id = range_id or None
    if range_id is None:
        return None
    exists = (await db.execute(
        select(CountryRange.id).where(
            CountryRange.id == range_id,
            CountryRange.country_id == country_id,
        )
    )).scalar_one_or_none()
    if exists is None:
        raise HTTPException(400, "Range does not belong to the selected country")
    return range_id


def _apply_filters(stmt, *, service_id, country_id, assigned, status, q, prefix):
    if service_id:
        stmt = stmt.where(Number.service_id == service_id)
    if country_id:
        stmt = stmt.where(Number.country_id == country_id)
    assigned = assigned or _assigned_filter(status)
    if assigned == "yes":
        stmt = stmt.where(Number.assigned_user_id.is_not(None))
    elif assigned == "no":
        stmt = stmt.where(Number.assigned_user_id.is_(None))
    if status == "disabled":
        stmt = stmt.where(Number.enabled == False)
    elif status == "used":
        stmt = stmt.where(Number.last_otp.is_not(None))
    elif status == "available":
        stmt = stmt.where(Number.enabled == True, Number.last_otp.is_(None), Number.assigned_user_id.is_(None))
    elif status == "reserved":
        stmt = stmt.where(Number.enabled == True, Number.last_otp.is_(None), Number.assigned_user_id.is_not(None))
    if q:
        stmt = stmt.where(Number.phone.ilike(f"%{q}%"))
    if prefix:
        cleaned = re.sub(r"\D", "", prefix)
        if cleaned:
            stmt = stmt.where(Number.phone.like(f"{cleaned}%"))
    return stmt


@router.get("")
async def list_numbers(
    service_id: int | None = None,
    country_id: int | None = None,
    assigned: str | None = None,
    status: str | None = None,
    q: str | None = None,
    prefix: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _: object = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    base = _apply_filters(select(Number), service_id=service_id, country_id=country_id,
                          assigned=assigned, status=status, q=q, prefix=prefix)
    total = (await db.execute(_apply_filters(select(func.count(Number.id)), service_id=service_id,
             country_id=country_id, assigned=assigned, status=status, q=q, prefix=prefix))).scalar() or 0
    limit = max(1, min(int(limit or 100), 1000))
    offset = max(0, int(offset or 0))
    rows = (await db.execute(base.order_by(Number.id.desc()).limit(limit).offset(offset))).scalars().all()
    items = [_d(n) for n in rows]
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


@router.post("/bulk-delete")
async def bulk_delete(
    body: dict,
    _: object = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import delete as sql_delete
    stmt = _apply_filters(
        select(Number.id),
        service_id=body.get("service_id"),
        country_id=body.get("country_id"),
        assigned=body.get("assigned"),
        status=body.get("status"),
        q=body.get("q"),
        prefix=body.get("prefix"),
    )
    # safety: require at least one filter to avoid wiping the whole table
    if not any(body.get(k) for k in ("service_id", "country_id", "status", "q", "prefix")):
        raise HTTPException(400, "Provide at least one filter (service/country/status/prefix/q).")
    ids = [row[0] for row in (await db.execute(stmt)).all()]
    if not ids:
        return {"deleted": 0}
    await db.execute(sql_delete(Number).where(Number.id.in_(ids)))
    await db.commit()
    return {"deleted": len(ids)}


@router.post("")
async def create_number(body: NumberIn, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    phone = re.sub(r"\D", "", body.phone)
    range_id = await _validated_range_id(db, body.country_id, body.range_id)
    n = Number(phone=phone, service_id=body.service_id, country_id=body.country_id,
               provider_id=body.provider_id, range_id=range_id, enabled=body.enabled)
    db.add(n)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Number already exists for this service")
    await db.refresh(n)
    return _d(n)


@router.post("/bulk")
async def bulk(body: BulkIn, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    raw = re.split(r"[\s,;]+", body.phones.strip())
    phones = [re.sub(r"\D", "", p) for p in raw if p.strip()]
    range_id = await _validated_range_id(db, body.country_id, body.range_id)
    unique_phones = list(dict.fromkeys(ph for ph in phones if ph))
    existing = set()
    if unique_phones:
        existing = set((await db.execute(
            select(Number.phone).where(
                Number.phone.in_(unique_phones),
                Number.service_id == body.service_id,
                Number.country_id == body.country_id,
                _range_match(range_id),
            )
        )).scalars().all())
    rows = [
        Number(phone=ph, service_id=body.service_id, country_id=body.country_id,
               provider_id=body.provider_id, range_id=range_id)
        for ph in unique_phones
        if ph not in existing
    ]
    db.add_all(rows)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "One or more numbers already exist for this service, country, and range")
    inserted = len(rows)
    return {"inserted": inserted, "submitted": len(phones)}


@router.put("/{nid}")
async def update_number(nid: int, body: NumberIn, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    n = (await db.execute(select(Number).where(Number.id == nid))).scalar_one_or_none()
    if not n:
        raise HTTPException(404)
    n.phone = re.sub(r"\D", "", body.phone)
    n.service_id = body.service_id
    n.country_id = body.country_id
    n.provider_id = body.provider_id
    n.range_id = body.range_id
    n.enabled = body.enabled
    await db.commit()
    await db.refresh(n)
    return _d(n)


@router.delete("/{nid}", status_code=204)
async def delete_number(nid: int, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    n = (await db.execute(select(Number).where(Number.id == nid))).scalar_one_or_none()
    if n:
        await db.delete(n)
        await db.commit()
