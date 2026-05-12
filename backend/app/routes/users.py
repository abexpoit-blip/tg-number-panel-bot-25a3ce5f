from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..db import get_db
from ..models import TgUser

router = APIRouter()


def _d(u: TgUser):
    return {
        "id": u.id,
        "tg_id": u.tg_id,
        "username": u.username,
        "first_name": u.first_name,
        "is_banned": u.is_banned,
        "balance": u.balance,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


class AdjustIn(BaseModel):
    delta: float


@router.get("")
async def list_users(q: str | None = None, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(TgUser)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(TgUser.username.ilike(like), TgUser.first_name.ilike(like)))
    rows = (await db.execute(stmt.order_by(TgUser.id.desc()).limit(500))).scalars().all()
    return [_d(u) for u in rows]


@router.post("/{uid}/adjust")
async def adjust(uid: int, body: AdjustIn, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    u = (await db.execute(select(TgUser).where(TgUser.id == uid))).scalar_one_or_none()
    if not u:
        raise HTTPException(404)
    u.balance = max(0.0, float(u.balance or 0) + float(body.delta))
    await db.commit()
    return _d(u)


@router.post("/{uid}/ban")
async def ban(uid: int, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    u = (await db.execute(select(TgUser).where(TgUser.id == uid))).scalar_one_or_none()
    if not u:
        raise HTTPException(404)
    u.is_banned = True
    await db.commit()
    return _d(u)


@router.post("/{uid}/unban")
async def unban(uid: int, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    u = (await db.execute(select(TgUser).where(TgUser.id == uid))).scalar_one_or_none()
    if not u:
        raise HTTPException(404)
    u.is_banned = False
    await db.commit()
    return _d(u)
