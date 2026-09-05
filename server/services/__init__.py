"""Servis katmani — router'lardan ayiklanmis, tek sorumluluklu yardimcilar.

Amac: router dosyalarini (ozellikle chats.py'deki uzun `send_message`) ince
tutmak; kompaktlama, RAG baglam derleme ve ortak yardimcilari (token/SSE)
ayri, test edilebilir ve yeniden kullanilabilir modullere tasimak.
"""
