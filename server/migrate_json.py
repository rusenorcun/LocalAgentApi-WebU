"""
Mevcut JSON dosyalarını (data/users.json + data/users/*/chat_*.json) SQLite DB'ye taşır.

Kullanım:
    python -m server.migrate_json [--dry-run]

Özellikler:
- İdempotent: zaten migrated kullanıcı/sohbetleri atlar
- Dry-run: DB'ye yazmadan sadece raporlar
- Orijinal JSON'lar data/backup_json/ altına arşivlenir (silinmez)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Proje kökünü sys.path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import config  # noqa: E402
from server.database import (  # noqa: E402
    Chat, Message, ModelCatalog, User, async_session_maker, init_db,
)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _detect_hash_algo(h: str) -> str:
    """bcrypt → 'bcrypt', argon2 → 'argon2id', diğer → 'unknown'."""
    if h.startswith("$2"):
        return "bcrypt"
    if h.startswith("$argon2"):
        return "argon2id"
    return "unknown"


async def _run(dry_run: bool) -> None:
    await init_db()

    users_file = config.USERS_FILE
    users_dir = config.USERS_DIR
    backup_dir = config.DATA_DIR / "backup_json"

    if not users_file.exists():
        print("users.json bulunamadı — migrasyon atlanıyor.")
        return

    with open(users_file, "r", encoding="utf-8") as f:
        users_data: dict = json.load(f)

    if not users_data:
        print("users.json boş — migrasyon atlanıyor.")
        return

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Migrasyon basliyor -> {config.DATA_DIR / 'chat.db'}")
    print(f"Kullanıcı sayısı: {len(users_data)}\n")

    users_migrated = 0
    chats_migrated = 0
    messages_migrated = 0
    skipped_users = 0

    async with async_session_maker() as session:
        from sqlalchemy import select

        for username, user_data in users_data.items():
            # Zaten var mı?
            result = await session.execute(
                select(User).where(User.username == username)
            )
            existing_user = result.scalar_one_or_none()

            if existing_user is not None:
                print(f"  [SKIP] Kullanıcı '{username}' zaten DB'de")
                skipped_users += 1
                db_user = existing_user
            else:
                pass_hash = user_data.get("password_hash", "")
                # bcrypt hash'i direkt taşı (giriş sırasında Argon2id'e re-hash yapılacak)
                role = "admin" if user_data.get("is_admin") else "user"

                db_user = User(
                    username=username,
                    pass_hash=pass_hash,
                    role=role,
                    created_at=_parse_dt(user_data.get("created_at")) or _now(),
                )
                print(f"  [USER] '{username}' (rol: {role}, hash: {_detect_hash_algo(pass_hash)})")

                if not dry_run:
                    session.add(db_user)
                    await session.flush()  # id almak için
                users_migrated += 1

            # Sohbet dosyalarını bul
            user_dir = users_dir / username
            if not user_dir.exists():
                continue

            chat_files = sorted(user_dir.glob("chat_*.json"))
            for chat_file in chat_files:
                try:
                    with open(chat_file, "r", encoding="utf-8") as f:
                        chat_data = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    print(f"    [WARN] {chat_file.name} okunamadı: {e}")
                    continue

                chat_id = chat_data.get("id")
                if not chat_id:
                    print(f"    [WARN] {chat_file.name} ID yok, atlanıyor")
                    continue

                # Sohbet zaten var mı?
                chat_result = await session.execute(
                    select(Chat).where(Chat.id == chat_id)
                )
                if chat_result.scalar_one_or_none() is not None:
                    print(f"    [SKIP] Sohbet {chat_id[:8]}… zaten DB'de")
                    continue

                messages = chat_data.get("messages", [])
                db_chat = Chat(
                    id=chat_id,
                    user_id=db_user.id if not dry_run else 0,
                    title=chat_data.get("title", "Yeni sohbet")[:120],
                    model=chat_data.get("model", config.MODEL_NAME),
                    pinned=False,
                    token_count=chat_data.get("token_count", 0),
                    summary=chat_data.get("summary") or None,
                    summarized_count=chat_data.get("summarized_count", 0),
                    created_at=_parse_dt(chat_data.get("created_at")) or _now(),
                    updated_at=_parse_dt(chat_data.get("updated_at")) or _now(),
                )

                print(f"    [CHAT] {chat_id[:8]}… '{db_chat.title[:40]}' — {len(messages)} mesaj")
                chats_migrated += 1

                if not dry_run:
                    session.add(db_chat)
                    await session.flush()

                    for msg in messages:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        tokens = msg.get("tokens", 0)
                        atts = msg.get("attachments")

                        db_msg = Message(
                            chat_id=chat_id,
                            role=role,
                            content=content,
                            tokens=tokens,
                            model=chat_data.get("model"),
                            attachments_json=json.dumps(atts, ensure_ascii=False) if atts else None,
                            created_at=_parse_dt(msg.get("ts")) or _now(),
                        )
                        session.add(db_msg)
                        messages_migrated += 1

        if not dry_run:
            await session.commit()

    # Arşivleme
    if not dry_run and (users_migrated > 0 or chats_migrated > 0):
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = backup_dir / ts
        archive.mkdir(parents=True, exist_ok=True)
        if users_file.exists():
            shutil.copy2(users_file, archive / "users.json")
        if users_dir.exists():
            shutil.copytree(users_dir, archive / "users", dirs_exist_ok=True)
        print(f"\nJSON yedekler -> {archive}")

    print("\n-- Ozet ----------------------------------------------")
    print(f"Migrated  : {users_migrated} kullanici, {chats_migrated} sohbet, {messages_migrated} mesaj")
    print(f"Atlandi   : {skipped_users} kullanici (zaten DB'de)")
    if dry_run:
        print("\n[DRY-RUN] DB degistirilmedi.")
    else:
        print("Migrasyon tamamlandi OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="JSON → SQLite migrasyon aracı")
    parser.add_argument("--dry-run", action="store_true", help="DB'ye yazmadan raporla")
    args = parser.parse_args()
    asyncio.run(_run(args.dry_run))


if __name__ == "__main__":
    main()
