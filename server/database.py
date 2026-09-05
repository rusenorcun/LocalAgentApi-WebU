"""SQLAlchemy 2 async motoru + tablo tanımları + session yardımcıları."""
from __future__ import annotations
import asyncio
import os

import json
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer,
    String, Text, func, text,
)
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from . import config

# ── Motor ──────────────────────────────────────────────────────────────────────

DB_PATH: Path = config.DATA_DIR / "chat.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


# ── ORM Modelleri ──────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True, nullable=False, index=True)
    pass_hash = Column(String(256), nullable=False)
    role = Column(String(16), nullable=False, default="user")  # user | admin
    theme_pref = Column(String(16), nullable=True)             # light | dark | system
    lang_pref = Column(String(8), nullable=True, default="tr") # tr | en
    default_model = Column(String(120), nullable=True)
    persona = Column(Text, nullable=True)  # tum sohbetlerde gecerli kullanici personasi
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)

    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    """Refresh token oturumları."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    refresh_hash = Column(String(256), nullable=False, unique=True)
    user_agent = Column(Text, nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="sessions")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(120), nullable=False, default="Yeni sohbet")
    model = Column(String(120), nullable=True)
    pinned = Column(Boolean, nullable=False, default=False)
    token_count = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)  # sohbete özel persona/sistem talimatı
    summarized_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat",
                            order_by="Message.created_at", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_chats_user_updated", "user_id", "updated_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), nullable=False)       # user | assistant | system
    content = Column(Text, nullable=False)
    tokens = Column(Integer, nullable=False, default=0)
    model = Column(String(120), nullable=True)
    attachments_json = Column(Text, nullable=True)  # JSON list
    sources_json = Column(Text, nullable=True)     # web/RAG kaynaklari: [{title,url?,snippet?}]
    parent_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=True)  # dallanma agaci
    active = Column(Boolean, nullable=False, default=True)        # kardesler arasinda secili dal
    hidden = Column(Boolean, nullable=False, default=False)       # UI'da gizli, baglamda kalir
    tool_calls_json = Column(Text, nullable=True)  # asistanin arac cagrilari (JSON)
    kind = Column(String(32), nullable=True)       # web_context | tool_result | None
    thinking = Column(Text, nullable=True)         # modelin dusunme sureci (reasoning)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chat = relationship("Chat", back_populates="messages")

    def attachments(self) -> list:
        if not self.attachments_json:
            return []
        try:
            return json.loads(self.attachments_json)
        except Exception:
            return []


class ModelCatalog(Base):
    """Admin yönetimli model kataloğu."""
    __tablename__ = "models"

    id = Column(Integer, primary_key=True)
    ollama_name = Column(String(120), unique=True, nullable=False)
    name_i18n_json = Column(Text, nullable=False, default="{}")   # {"tr": "...", "en": "..."}
    desc_i18n_json = Column(Text, nullable=False, default="{}")
    strengths_json = Column(Text, nullable=False, default="[]")   # ["Muhakeme", ...]
    speed = Column(Integer, nullable=False, default=3)            # 1-5
    is_default = Column(Boolean, nullable=False, default=False)
    is_vision = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    internal = Column(Boolean, nullable=False, default=False)     # kullanıcıya gösterilmez
    supports_tools = Column(Boolean, nullable=False, default=False)  # /api/show ile dinamik
    # Model bazlı üretim ayarları (None = global config değeri kullanılır).
    # tune_auto=True iken başlangıçta VRAM'e göre otomatik hesaplanır
    # (services/model_tuner.py); admin manuel değer verirse tune_auto=False olur.
    num_ctx = Column(Integer, nullable=True)
    num_gpu = Column(Integer, nullable=True)
    tune_auto = Column(Boolean, nullable=False, default=True)


class Document(Base):
    """RAG belge hafızası."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scope = Column(String(16), nullable=False, default="private")  # private | shared
    name = Column(String(256), nullable=False)
    mime = Column(String(128), nullable=True)
    size = Column(BigInteger, nullable=False, default=0)
    path = Column(String(512), nullable=False)
    status = Column(String(32), nullable=False, default="processing")  # processing | ready | error
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    """RAG metin parçaları (embedding sqlite-vec'te tutulur)."""
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    seq = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=True)  # JSON float list

    document = relationship("Document", back_populates="chunks")


class ChatSummarySnapshot(Base):
    __tablename__ = "chat_summary_snapshots"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(256), nullable=False)
    source_chat_ids = Column(Text, nullable=False)  # JSON array of chat IDs
    summary_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)   # UUID
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProjectChat(Base):
    __tablename__ = "project_chats"

    id = Column(Integer, primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chat_id = Column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        Index("ix_project_chats_pc", "project_id", "chat_id", unique=True),
    )


class ProjectDocument(Base):
    __tablename__ = "project_documents"

    id = Column(Integer, primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        Index("ix_project_docs_pd", "project_id", "document_id", unique=True),
    )


class ApiKey(Base):
    """Kisisel programatik API anahtarlari."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(80), nullable=False)
    key_hash = Column(String(256), nullable=False, unique=True, index=True)
    scopes = Column(String(256), nullable=False, default="")  # virgulle ayrilmis liste; bos=tam erisim
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="api_keys")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(32), nullable=True)
    ip = Column(String(64), nullable=True)
    action = Column(String(64), nullable=False, index=True)
    detail = Column(Text, nullable=True)


class Settings(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)


# ── DB Başlatma ────────────────────────────────────────────────────────────────

# ── Dangling dosya temizligi: Document silinince diskteki dosyayi da kaldir ──
@event.listens_for(Document, "after_delete")
def _document_file_cleanup(mapper, connection, target):
    try:
        if target.path and os.path.isfile(target.path):
            os.remove(target.path)
    except Exception:
        pass


async def init_db() -> None:
    """Alembic migration uygula (yoksa create_all fallback) + WAL + FTS5."""
    # Alembic ile migrate et
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command as alembic_command
        import os as _os

        ini_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "alembic.ini")
        if _os.path.exists(ini_path):
            alembic_cfg = AlembicConfig(ini_path)
            # alembic.ini'deki URL ve script_location'ı mutlak path'e ayarla
            alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
            project_root = _os.path.dirname(_os.path.dirname(__file__))
            alembic_cfg.set_main_option("script_location", _os.path.join(project_root, "alembic"))

            # Tablolar create_all ile oluşmuş ama alembic_version damgası yoksa:
            # upgrade "table already exists" ile patlar. Önce damgala.
            async with engine.connect() as conn:
                has_users = (await conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
                ))).first() is not None
                has_ver = (await conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
                ))).first() is not None
            if has_users and not has_ver:
                await asyncio.to_thread(alembic_command.stamp, alembic_cfg, "head")
            else:
                await asyncio.to_thread(alembic_command.upgrade, alembic_cfg, "head")
        else:
            # Fallback: alembic.ini yoksa create_all
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning(f"Alembic migration atlandı ({_e}), create_all deneniyor")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        # WAL modu — eşzamanlı okuma için
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        # FTS5 tam metin arama (messages tablosu üzerine)
        await conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts "
            "USING fts5(content, content='messages', content_rowid='id', "
            "tokenize='unicode61')"
        ))
        # FTS senkronizasyon trigger'ları
        await conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
            END
        """))
        await conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES ('delete', old.id, old.content);
            END
        """))
        await conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES ('delete', old.id, old.content);
                INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
            END
        """))
        # M1: RAG belge işleme fire-and-forget çalışır; sunucu işlem ortasında
        # yeniden başlarsa belge sonsuza dek 'processing*' durumunda takılırdı.
        # Başlangıçta yarım kalanları 'error'a çek — kullanıcı yeniden yükleyebilir.
        try:
            await conn.execute(text(
                "UPDATE documents SET status='error' WHERE status LIKE 'processing%'"
            ))
        except Exception:
            pass  # documents tablosu henüz yoksa sorun değil
        # Model bazlı ayar kolonları (eski DB'lere ekleme — SQLite additive ALTER)
        for _ddl in (
            "ALTER TABLE models ADD COLUMN num_ctx INTEGER",
            "ALTER TABLE models ADD COLUMN num_gpu INTEGER",
            "ALTER TABLE models ADD COLUMN tune_auto BOOLEAN NOT NULL DEFAULT 1",
        ):
            try:
                await conn.execute(text(_ddl))
            except Exception:
                pass  # kolon zaten var
    await _seed_model_catalog()
    await _backfill_vision_flags()
    await _sync_catalog_state()
    await _update_tool_capabilities()
    # Model bazlı otomatik num_ctx/num_gpu hesabı (VRAM'e göre)
    try:
        from .services.model_tuner import auto_tune_models
        await auto_tune_models()
    except Exception:
        import logging as _log
        _log.getLogger(__name__).warning("Model auto-tune atlandı", exc_info=True)


async def _update_tool_capabilities() -> None:
    """Ollama /api/show ile modellerin tools destegini gunceller. Erisilemezse dokunmaz."""
    import httpx
    from sqlalchemy import select
    try:
        async with async_session_maker() as session:
            models = (await session.execute(select(ModelCatalog))).scalars().all()
            async with httpx.AsyncClient(timeout=5.0) as client:
                for m in models:
                    try:
                        r = await client.post(f"{config.OLLAMA_HOST}/api/show",
                                              json={"model": m.ollama_name})
                        if r.status_code == 200:
                            data = r.json()
                            caps = data.get("capabilities", []) or []
                            tmpl = data.get("template", "") or ""
                            supports = ("tools" in caps) or ("{{.Tools}}" in tmpl) \
                                or ("{{ .Tools }}" in tmpl) or ("{{- .Tools" in tmpl)
                            if m.supports_tools != supports:
                                m.supports_tools = supports
                    except Exception:
                        pass
            await session.commit()
    except Exception:
        pass


# ── Model Kataloğu (tek kaynak) ───────────────────────────────────────────────
# Yonetilen modeller: isim/aciklama/roller burada tanimli. Hem fresh seed hem de
# mevcut DB senkronu bu listeyi kullanir (isim degisikligi mevcut kurulumlara da yansir).
_MANAGED_CATALOG = [
    {
        "ollama_name": "qwen3.6:35b-a3b-q4_K_M",
        "name_i18n_json": '{"tr": "Atlas", "en": "Atlas"}',
        "desc_i18n_json": '{"tr": "Ana model — günlük kullanım, araştırma, yazım ve genel görevler için dengeli ve güçlü (MoE).", "en": "Main model — balanced and powerful for daily use, research, writing and general tasks (MoE)."}',
        "strengths_json": '["Genel", "Muhakeme", "Uzun bağlam"]',
        "speed": 4, "is_default": True, "is_vision": False, "enabled": True, "internal": False,
    },
    {
        "ollama_name": "gpt-oss:120b",
        "name_i18n_json": '{"tr": "Mergen", "en": "Mergen"}',
        "desc_i18n_json": '{"tr": "Derin muhakeme ve çok adımlı planlama uzmanı; en güçlü ama yavaş. Karmaşık analiz için.", "en": "Deep reasoning and multi-step planning specialist; most capable but slow. For complex analysis."}',
        "strengths_json": '["Derin muhakeme", "Planlama"]',
        "speed": 1, "is_default": False, "is_vision": False, "enabled": True, "internal": False,
    },
    {
        "ollama_name": "qwen3-coder:30b",
        "name_i18n_json": '{"tr": "Kayra", "en": "Kayra"}',
        "desc_i18n_json": '{"tr": "Kod yazma, hata ayıklama, refactor ve agentic kod görevleri. Hızlı (MoE).", "en": "Code generation, debugging, refactoring and agentic coding tasks. Fast (MoE)."}',
        "strengths_json": '["Kod", "Agentic", "Hız"]',
        "speed": 4, "is_default": False, "is_vision": False, "enabled": True, "internal": False,
    },
    {
        "ollama_name": "qwen3-vl:30b-a3b-instruct",
        "name_i18n_json": '{"tr": "Tepegöz", "en": "Tepegoz"}',
        "desc_i18n_json": '{"tr": "Görsel anlama: ekran görüntüsü, belge, fotoğraf analizi ve OCR.", "en": "Visual understanding: screenshots, documents, photo analysis and OCR."}',
        "strengths_json": '["Görsel analiz", "OCR", "Multimodal"]',
        "speed": 3, "is_default": False, "is_vision": True, "enabled": True, "internal": False,
    },
    {
        "ollama_name": "mistral-small3.1:24b",
        "name_i18n_json": '{"tr": "Korkut Ata", "en": "Korkut Ata"}',
        "desc_i18n_json": '{"tr": "Hızlı genel amaçlı — araştırma, özetleme, PDF/belge ve görsel destekli. Akıcı.", "en": "Fast general-purpose — research, summarization, PDF/docs, vision-capable. Smooth."}',
        "strengths_json": '["Hız", "Genel", "Görsel"]',
        "speed": 4, "is_default": False, "is_vision": True, "enabled": True, "internal": False,
    },
    {
        "ollama_name": "qwen3-vl:8b",
        "name_i18n_json": '{"tr": "Görü Mini", "en": "Vision Mini"}',
        "desc_i18n_json": '{"tr": "Dahili görsel→metin (caption): yüklenen görselleri otomatik betimler.", "en": "Internal image-to-text (caption): automatically describes uploaded images."}',
        "strengths_json": '["Görsel→metin", "Hız"]',
        "speed": 5, "is_default": False, "is_vision": True, "enabled": True, "internal": True,
    },
]

# Geriye donuk uyumluluk icin alias.
_DEFAULT_CATALOG = _MANAGED_CATALOG

# Artik kaldirilmis (Ollama'dan silinmis) modeller — secicide gorunup hata vermesin.
_REMOVED_MODELS = ("qwen3:32b", "qwen2.5-coder:32b", "devstral:24b")

# Senkronda mevcut satirda guncellenecek alanlar (enabled/is_default admin'e birakilir).
_SYNC_FIELDS = ("name_i18n_json", "desc_i18n_json", "strengths_json", "speed", "is_vision", "internal")


async def _seed_model_catalog() -> None:
    """Katalog bosken yonetilen modelleri ekler (varsa dokunmaz)."""
    from sqlalchemy import select
    async with async_session_maker() as session:
        count = (await session.execute(select(func.count()).select_from(ModelCatalog))).scalar()
        if count and count > 0:
            return
        for entry in _MANAGED_CATALOG:
            session.add(ModelCatalog(**entry))
        await session.commit()


async def _backfill_vision_flags() -> None:
    """VL/vision modellerini is_vision=True yap (eski kurulumlarda eksik kalmis olabilir)."""
    from sqlalchemy import or_, update as _update
    async with async_session_maker() as session:
        patterns = ["%-vl%", "%vl:%", "%vision%", "%llava%", "%minicpm-v%", "%moondream%"]
        conds = [ModelCatalog.ollama_name.ilike(p) for p in patterns]
        await session.execute(_update(ModelCatalog).where(or_(*conds)).values(is_vision=True))
        await session.commit()


async def _sync_catalog_state() -> None:
    """Mevcut kurulumlari yonetilen listeyle hizalar (idempotent):
      - Yonetilen model varsa isim/aciklama/rol alanlarini gunceller (rename mevcut DB'ye de yansir),
        yoksa ekler.
      - Artik yuklu olmayan modelleri gizler (enabled=False) — secicide hata vermesin.
    """
    from sqlalchemy import select, update as _update
    async with async_session_maker() as session:
        for entry in _MANAGED_CATALOG:
            existing = (await session.execute(
                select(ModelCatalog).where(ModelCatalog.ollama_name == entry["ollama_name"])
            )).scalar_one_or_none()
            if existing:
                for f in _SYNC_FIELDS:
                    setattr(existing, f, entry[f])
            else:
                session.add(ModelCatalog(**entry))
        await session.execute(
            _update(ModelCatalog)
            .where(ModelCatalog.ollama_name.in_(_REMOVED_MODELS))
            .values(enabled=False)
        )
        await session.commit()
