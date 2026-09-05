"""Veritabanina dogrudan admin kullanici ekler (kayit kapaliyken / admin yokken kullanin).

Kullanim (proje klasorunde, venv aktifken):
    .venv\\Scripts\\python.exe create_admin.py <kullanici_adi> <sifre>

Ornek:
    .venv\\Scripts\\python.exe create_admin.py rusen GucluBirSifre123

Sunucu calisirken de calistirilabilir (WAL modu ayni anda yazmaya izin verir).
"""
import asyncio
import sys

from sqlalchemy import select

from server.auth_v2 import hash_password
from server.database import User, async_session_maker, init_db


async def main(username: str, password: str) -> None:
    if len(username) < 3 or len(password) < 8:
        print("Kullanici adi >=3, sifre >=8 karakter olmali.")
        sys.exit(1)

    # Tablolar yoksa olustur / migrate et (sunucu hic calismadiysa diye).
    await init_db()

    async with async_session_maker() as session:
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()

        if existing:
            existing.pass_hash = hash_password(password)
            existing.role = "admin"
            await session.commit()
            print(f"Mevcut kullanici '{username}' guncellendi -> role=admin, sifre yenilendi.")
            return

        user = User(username=username, pass_hash=hash_password(password), role="admin")
        session.add(user)
        await session.commit()
        print(f"Admin kullanici olusturuldu: {username}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Kullanim: python create_admin.py <kullanici_adi> <sifre>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
