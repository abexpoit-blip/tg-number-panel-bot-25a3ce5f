from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..db import get_db
from ..emoji import clean_custom_emoji_id
from ..models import Service

router = APIRouter()


class ServiceIn(BaseModel):
    name: str
    keyword: str
    emoji: str = "📱"
    custom_emoji_id: str | None = None
    icon_mode: str = "auto"
    enabled: bool = True
    sort_order: int = 0


_ALLOWED_MODES = {"auto", "custom", "brand", "default"}


def _to_dict(s: Service):
    return {
        "id": s.id, "name": s.name, "keyword": s.keyword, "emoji": s.emoji,
        "custom_emoji_id": s.custom_emoji_id,
        "icon_mode": getattr(s, "icon_mode", None) or "auto",
        "enabled": s.enabled, "sort_order": s.sort_order,
    }


@router.get("")
async def list_services(_: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Service).order_by(Service.sort_order, Service.id))).scalars().all()
    return [_to_dict(s) for s in rows]


@router.post("")
async def create_service(body: ServiceIn, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    data = body.model_dump()
    data["custom_emoji_id"] = clean_custom_emoji_id(data.get("custom_emoji_id"))
    s = Service(**data)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _to_dict(s)


@router.put("/{sid}")
async def update_service(sid: int, body: ServiceIn, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Service).where(Service.id == sid))).scalar_one_or_none()
    if not s:
        raise HTTPException(404)
    data = body.model_dump()
    data["custom_emoji_id"] = clean_custom_emoji_id(data.get("custom_emoji_id"))
    for k, v in data.items():
        setattr(s, k, v)
    await db.commit()
    return _to_dict(s)


@router.delete("/{sid}", status_code=204)
async def delete_service(sid: int, _: object = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Service).where(Service.id == sid))).scalar_one_or_none()
    if s:
        await db.delete(s)
        await db.commit()
