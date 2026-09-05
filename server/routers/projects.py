"""API v2 — Proje CRUD + sohbet/belge bağlama."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_v2 import current_user
from ..database import (
    Project, ProjectChat, ProjectDocument,
    Chat, Document, User, get_session,
)

router = APIRouter(prefix="/api/v2/projects", tags=["projects"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Şemalar ───────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None


class ChatLink(BaseModel):
    chat_id: str


class DocLink(BaseModel):
    doc_id: int


# ── Yardımcı ──────────────────────────────────────────────────────────────────

async def _project_out(p: Project, db: AsyncSession) -> dict:
    cc = (await db.execute(
        select(func.count()).select_from(ProjectChat).where(ProjectChat.project_id == p.id)
    )).scalar() or 0
    dc = (await db.execute(
        select(func.count()).select_from(ProjectDocument).where(ProjectDocument.project_id == p.id)
    )).scalar() or 0
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "chat_count": cc,
        "doc_count": dc,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def _get_project(project_id: str, user: User, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Proje bulunamadı")
    return p


# ── Uç noktalar ───────────────────────────────────────────────────────────────

@router.get("")
async def list_projects(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return [await _project_out(p, db) for p in projects]


@router.post("")
async def create_project(
    body: ProjectCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    p = Project(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name=body.name,
        description=body.description,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return await _project_out(p, db)


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    body: ProjectPatch,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    p = await _get_project(project_id, user, db)
    if body.name is not None:
        p.name = body.name
    if body.description is not None:
        p.description = body.description
    p.updated_at = _now()
    await db.commit()
    return await _project_out(p, db)


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    p = await _get_project(project_id, user, db)
    await db.delete(p)
    await db.commit()
    return {"deleted": True}


# ── Sohbet bağlama ────────────────────────────────────────────────────────────

@router.post("/{project_id}/chats")
async def add_chat_to_project(
    project_id: str,
    body: ChatLink,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    p = await _get_project(project_id, user, db)

    # Sohbet bu kullanıcıya ait mi?
    chat_res = await db.execute(
        select(Chat).where(Chat.id == body.chat_id, Chat.user_id == user.id)
    )
    if not chat_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")

    # Zaten bağlıysa atla
    existing = await db.execute(
        select(ProjectChat).where(
            ProjectChat.project_id == p.id,
            ProjectChat.chat_id == body.chat_id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(ProjectChat(project_id=p.id, chat_id=body.chat_id))
        await db.commit()

    return {"linked": True}


@router.delete("/{project_id}/chats/{chat_id}")
async def remove_chat_from_project(
    project_id: str,
    chat_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _get_project(project_id, user, db)
    result = await db.execute(
        select(ProjectChat).where(
            ProjectChat.project_id == project_id,
            ProjectChat.chat_id == chat_id,
        )
    )
    pc = result.scalar_one_or_none()
    if pc:
        await db.delete(pc)
        await db.commit()
    return {"unlinked": True}


# ── Belge bağlama ─────────────────────────────────────────────────────────────

@router.get("/{project_id}/documents")
async def get_project_documents(
    project_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _get_project(project_id, user, db)
    result = await db.execute(
        select(Document)
        .join(ProjectDocument, ProjectDocument.document_id == Document.id)
        .where(ProjectDocument.project_id == project_id)
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "size": d.size,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.post("/{project_id}/documents")
async def add_doc_to_project(
    project_id: str,
    body: DocLink,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    p = await _get_project(project_id, user, db)

    # Belge bu kullanıcıya ait mi?
    doc_res = await db.execute(
        select(Document).where(Document.id == body.doc_id, Document.user_id == user.id)
    )
    if not doc_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Belge bulunamadı")

    existing = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.project_id == p.id,
            ProjectDocument.document_id == body.doc_id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(ProjectDocument(project_id=p.id, document_id=body.doc_id))
        await db.commit()

    return {"linked": True}


@router.delete("/{project_id}/documents/{doc_id}")
async def remove_doc_from_project(
    project_id: str,
    doc_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    await _get_project(project_id, user, db)
    result = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.document_id == doc_id,
        )
    )
    pd = result.scalar_one_or_none()
    if pd:
        await db.delete(pd)
        await db.commit()
    return {"unlinked": True}
