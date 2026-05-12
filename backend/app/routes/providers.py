from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_admin
from ..db import get_db
from ..models import Provider

router = APIRouter()


@router.get("")
async def list_providers(_: dict = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Provider).order_by(Provider.id))).scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "type": p.type,
            "currency": p.currency,
            "enabled": p.enabled,
            "base_url": p.base_url,
        }
        for p in rows
    ]
