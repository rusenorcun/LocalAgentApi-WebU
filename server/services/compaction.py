"""Sohbet kompaktlama (ozetleme) DB islemleri.

Pencereye sigmayan eski mesajlar bir ozete katlanir; bu modul ozeti DB'ye
yazar, eski mesajlari siler ve token sayacini gunceller. Ozet uretimi (model
cagrisi) `server.chat.summarize_overflow` icinde; burada yalniz DB tarafi var.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import Chat, Message
from .text_utils import estimate_tokens


async def apply_compaction_db(
    db: AsyncSession,
    c: Chat,
    all_messages: list[Message],
    summary: str,
    new_sc: int,
) -> dict:
    """Ozetlenen eski mesajlari siler, ozeti sistem mesaji olarak ekler, token gunceller.

    Parametreler:
      db           : aktif async oturum
      c            : sohbet ORM nesnesi (yerinde guncellenir)
      all_messages : sohbetin (eskiden yeniye) tum mesajlari
      summary      : uretilen ozet metni
      new_sc       : `all_messages` icinde bu indekse kadar olanlar ozetlenip silinir

    NOT: Index uzayinin `all_messages` ile birebir hizali olmasi sarttir; cagiran
    taraf ozeti RAG/web baglami EKLENMEMIS temiz gecmis uzerinde hesaplamalidir
    (aksi halde yanlis mesajlar silinir).
    """
    # Sistem mesaji daima pencerede kalir; ozetlemeye 1. indeksten baslanir.
    start_idx = c.summarized_count
    if all_messages and all_messages[0].role == "system" and c.summarized_count == 0:
        start_idx = 1

    # Ozetlenecek (silinecek) eski mesajlar.
    to_delete = all_messages[start_idx:new_sc]
    for m in to_delete:
        await db.delete(m)

    # Ozeti, UI'da da gorunsun diye 'system' mesaji olarak sakla.
    summary_msg = Message(
        chat_id=c.id,
        role="system",
        content="**Sistem Özeti:**\n" + summary,
        tokens=estimate_tokens(summary),
        model=c.model,
    )
    db.add(summary_msg)

    # Silindigi icin surekli-ozet alanlari sifirlanir (yeni cursor 0).
    c.summary = ""
    c.summarized_count = 0

    # Kalan mesajlarin + ozetin tahmini token toplami.
    remaining_msgs = [m for m in all_messages if m not in to_delete]
    c.token_count = sum(m.tokens for m in remaining_msgs) + summary_msg.tokens

    return {"summary": "", "summarized_count": 0, "token_count": c.token_count}
