"""Uretim penceresi matematiği (kayan pencere + tasma hesabi).

ESKI NOT: Bu fonksiyonlar v1 JSON deposundan (server/storage.py) buraya
tasindi; modul silindikten sonra pencere/islem matematiginin tek yurdur.
Davlaniş birebir korunmustur (testler: test_windowing_parity).

  * build_window      -> modele gidecek mesaj listesi (ozet + sigacak kuyruk)
  * overflow_messages -> pencereye sigmayan, ozetlenecek eski mesajlar
Token tahmini text_utils.estimate_tokens'tan gelir (tek kaynak).
"""
from __future__ import annotations

from typing import Optional

from .. import config
from .text_utils import estimate_tokens

__all__ = ["build_window", "overflow_messages", "estimate_tokens"]


def _msg_tokens(m: dict) -> int:
    return m.get("tokens", estimate_tokens(m["content"]))


def _content_with_attachments(m: dict) -> str:
    """Mesaj icerigine ekli dosya metnini ekler (modele gonderim icin)."""
    content = m["content"]
    for a in m.get("attachments", []):
        name = a.get("name", "dosya")
        text = a.get("text", "")
        nimg = a.get("num_images", 0)
        parts = [f"\n\n[Ekli dosya: {name}]"]
        if nimg:
            parts.append(f"({nimg} gorsel ayrica goruntu olarak eklendi)")
        if text:
            parts.append("\n" + text)
        content += " ".join(parts)
    return content


def overflow_messages(chat: dict, budget: Optional[int] = None) -> tuple[int, list[dict]]:
    """
    Ozetlenmemis mesajlardan pencereye SIGMAYAN en eskileri dondurur.
    Donus: (yeni_summarized_count, ozetlenecek_mesajlar).
    Bos liste -> kompaktlama gerekmiyor.
    """
    if budget is None:
        budget = config.NUM_CTX - config.CTX_RESERVE
    if chat.get("summary"):
        budget -= config.SUMMARY_RESERVE

    msgs = chat.get("messages", [])
    sc = chat.get("summarized_count", 0)
    system_tok = 0
    start = sc
    if msgs and msgs[0]["role"] == "system" and sc == 0:
        system_tok = _msg_tokens(msgs[0])
        start = 1  # sistem mesaji daima pencerede, ozetlenmez

    # En yeni COMPACT_KEEP_RECENT mesaj daima ham kalir
    keep = config.COMPACT_KEEP_RECENT
    used = system_tok
    # Sondan basa dogru sigani topla
    fit_from = len(msgs)  # bu indeksten itibaren pencerede
    for i in range(len(msgs) - 1, start - 1, -1):
        t = _msg_tokens(msgs[i])
        recent_rank = len(msgs) - i  # 1 = en yeni
        if used + t > budget and recent_rank > keep:
            break
        used += t
        fit_from = i
    if fit_from <= start:
        return sc, []  # her sey sigiyor
    to_summarize = msgs[start:fit_from]
    return fit_from, to_summarize


def build_window(chat: dict, budget: Optional[int] = None) -> list[dict]:
    """Kayan pencere: ozet (varsa) + num_ctx'e sigacak son mesajlar."""
    if budget is None:
        budget = config.NUM_CTX - config.CTX_RESERVE
    msgs = chat.get("messages", [])
    sc = chat.get("summarized_count", 0)
    summary = chat.get("summary", "")

    out: list[dict] = []
    used = 0

    # Sistem mesaji (varsa daima ilk)
    system = None
    if msgs and msgs[0]["role"] == "system":
        system = msgs[0]
        out.append({"role": "system", "content": system["content"]})
        used += _msg_tokens(system)

    # Surekli ozet -> sistem baglami olarak
    if summary:
        sm = {"role": "system", "content": "Onceki konusmanin ozeti:\n" + summary}
        out.append(sm)
        used += estimate_tokens(sm["content"])

    # Ozetlenmemis son mesajlar (sistem haric)
    start = sc if sc > 0 else (1 if system else 0)
    tail = msgs[start:]
    selected: list[dict] = []
    for m in reversed(tail):
        t = _msg_tokens(m)
        if used + t > budget and selected:
            break
        selected.append(m)
        used += t
    selected.reverse()
    out.extend({"role": m["role"], "content": _content_with_attachments(m)} for m in selected)
    return out
