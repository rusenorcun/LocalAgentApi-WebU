import uuid
from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session, User, ChatSummarySnapshot
from ..auth_v2 import current_user

router = APIRouter()

class SummaryOut(BaseModel):
    id: str
    title: str
    summary_text: str
    source_chat_ids: str
    created_at: Any

@router.get("", response_model=List[SummaryOut])
async def list_summaries(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session)
):
    res = await db.execute(
        select(ChatSummarySnapshot)
        .where(ChatSummarySnapshot.user_id == user.id)
        .order_by(ChatSummarySnapshot.created_at.desc())
    )
    return [
        SummaryOut(
            id=s.id,
            title=s.title,
            summary_text=s.summary_text,
            source_chat_ids=s.source_chat_ids,
            created_at=s.created_at
        ) for s in res.scalars().all()
    ]

@router.delete("/{summary_id}")
async def delete_summary(
    summary_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session)
):
    res = await db.execute(
        select(ChatSummarySnapshot)
        .where(ChatSummarySnapshot.id == summary_id, ChatSummarySnapshot.user_id == user.id)
    )
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Özet bulunamadı")
    await db.delete(s)
    await db.commit()
    return {"success": True}
