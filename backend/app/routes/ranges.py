from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..db import get_db
from ..models import CountryRange

router = APIRouter()


class RangeIn(BaseModel):
    country_id: int
    name: str
    prefix: str = ""
    sort_order: int = 0
    enabled: bool = True


def _d(r: CountryRange) -> dict:
    return {
        "id": r.id,
        "country_id": r.country_id,
        "name": r.name,
        "prefix": r.prefix,
        "sort_order": r.sort_order,
        "enabled": r.enabled,
        "country_name": r.country.name if r.country else None,
        "country_flag": r.country.flag if r.country else None,
    }


@router.get("")
async def list_ranges(
    country_id: int | None = None,
    _: object = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CountryRange)
    if country_id:
        stmt = stmt.where(CountryRange.country_id == country_id)
    rows = (await db.execute(stmt.order_by(CountryRange.country_id, CountryRange.sort_order, CountryRange.id))).scalars().all()
    return [_d(r) for r in rows]


@router.post("")
async def create_range(body: RangeIn, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "Name is required")
    r = CountryRange(
        country_id=body.country_id,
        name=name,
        prefix=(body.prefix or "").strip(),
        sort_order=body.sort_order or 0,
        enabled=body.enabled,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return _d(r)


@router.put("/{rid}")
async def update_range(rid: int, body: RangeIn, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(CountryRange).where(CountryRange.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404)
    r.country_id = body.country_id
    r.name = (body.name or "").strip() or r.name
    r.prefix = (body.prefix or "").strip()
    r.sort_order = body.sort_order or 0
    r.enabled = body.enabled
    await db.commit()
    await db.refresh(r)
    return _d(r)


@router.delete("/{rid}", status_code=204)
async def delete_range(rid: int, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(CountryRange).where(CountryRange.id == rid))).scalar_one_or_none()
    if r:
        await db.delete(r)
        await db.commit()
