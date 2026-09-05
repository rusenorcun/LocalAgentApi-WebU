"""Ortak kucuk yardimcilar: SSE bicimleme + token tahmini + metin kurallari.

Bu fonksiyonlar birden cok router/serviste kullanildigindan tek yerde toplandi.
"""
import json
import re

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def valid_username(username: str) -> bool:
    """Kullanici adi kurali: 3-32 karakter, harf/rakam/._- (v1'den devir)."""
    return bool(_USERNAME_RE.match(username or ""))


def sse(event: dict) -> str:
    """Bir olay sozlugunu Server-Sent-Events (SSE) 'data:' satirina cevirir.

    Tarayici EventSource/`fetch` stream tarafi her olayi `data: {...}\\n\\n`
    biciminde bekler. `ensure_ascii=False` ile Turkce karakterler bozulmaz.
    """
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def estimate_tokens(text: str) -> int:
    """Metin icin kaba token tahmini (~3.5 karakter/token).

    Gercek tokenizer cagirmak pahali; pencere/limit hesaplari icin bu yaklasim
    yeterli. En az 1 doner (bos olmayan her mesaj >=1 token sayilsin).
    """
    return max(1, round(len(text) / 3.5))


def derive_title(text: str, max_len: int = 60) -> str:
    """Asistan yanitindan MODELSIZ sohbet basligi turer.

    Eski hali kucuk bir modeli cagiriyordu — tek GPU'da ana modeli bosaltip
    yeniden yukletiyordu (gereksiz takas). Artik saf metin isleme:
      * markdown/code fence/heading/baslik-on-ekleri temizlenir
      * ilk anlamlı satir alinir, kelime sinirinda kirpilir
    Anlamlı bir satir yoksa "" doner (cagiran mevcut basligi korur).
    """
    if not text:
        return ""
    in_code = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Kod blogu fence'i: icerigi de atla (print(...) baslik olmaz)
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        # Tablo / alinti satirlarini atla
        if line.startswith(("|", ">")):
            continue
        # Baslik on eklerini ve markdown vurgusunu temizle
        line = line.lstrip("*_#>- ").strip()
        for pref in ("Başlık:", "Baslik:", "Title:", "Konu:", "Özet:", "Ozet:"):
            if line.lower().startswith(pref.lower()):
                line = line[len(pref):].strip()
        # Kalin/vurgu isaretlerini soy
        line = line.strip("*_`").strip()
        # Cümle sonunu bul: ilk nokta/soru/unlem ya da max_len
        cut = len(line)
        for punct in ("?", "!", "."):
            idx = line.find(punct)
            if idx != -1:
                cut = min(cut, idx + 1)
                break
        line = line[:cut].strip()
        # Kelime sinirinda kirp
        if len(line) > max_len:
            line = line[:max_len].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        # En az 8 karakterlik anlamli bir sey uretmedikse vazgec
        if len(line.replace("…", "").strip()) >= 8:
            # Baslikta sondaki nokta durmaz (soru/unlem kalir)
            if line.endswith(".") and not line.endswith("…"):
                line = line[:-1].rstrip()
            return line[:max_len + 1]
        return ""  # ilk anlamlı satir kullanilamazsa deneme devam etmesin
    return ""
