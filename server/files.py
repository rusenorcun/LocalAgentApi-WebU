"""Dosya cikarma hatti: markitdown ile metin + PyMuPDF/zip ile gorsel.

Akilli strateji:
 - PDF sayfasinda metin varsa -> gomulu gorselleri cikar
 - sayfa metinsiz (taranmis) ise -> tum sayfayi resme cevir
 - Office (docx/pptx/xlsx) -> markitdown metin + zip icindeki medya gorselleri
 - Duz gorsel -> dogrudan
 - Metin (txt/md/csv/...) -> dogrudan oku
Gorseller ~IMAGE_MAX_EDGE'e kucultulup JPEG/base64'e cevrilir.
"""
import base64
import hashlib
import io
import re
import uuid
import zipfile
from pathlib import Path
from typing import Optional, Callable

from . import config

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
try:
    from PIL import Image
except ImportError:
    Image = None
try:
    from markitdown import MarkItDown
    _md = MarkItDown()
except Exception:
    _md = None

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".json", ".html", ".htm"}
OFFICE_EXTS = {".docx", ".pptx", ".xlsx"}
OFFICE_MEDIA_DIRS = {".docx": "word/media/", ".pptx": "ppt/media/", ".xlsx": "xl/media/"}


def _safe_name(name: str) -> str:
    name = Path(name).name
    return re.sub(r"[^A-Za-z0-9_.\- ]", "_", name)[:120] or "dosya"


def _img_to_b64(im: "Image.Image", edge: int = None) -> Optional[str]:
    if Image is None:
        return None
    try:
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        w, h = im.size
        edge = edge or config.IMAGE_MAX_EDGE
        if max(w, h) > edge:
            scale = edge / max(w, h)
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _bytes_to_b64(data: bytes, edge: int = None) -> Optional[str]:
    if Image is None or not data:
        return None
    try:
        return _img_to_b64(Image.open(io.BytesIO(data)), edge)
    except Exception:
        return None


def _filtered_b64(data: bytes, seen: set, edge: int = None) -> Optional[str]:
    """Gomulu/medya gorseli icin: cok kucukleri (logo/ikon) atla + tekrari ele.

    Sinirli gorsel slotlarinin gercek sekil/grafiklere gitmesini saglar.
    """
    if Image is None or not data:
        return None
    try:
        im = Image.open(io.BytesIO(data))
        w, h = im.size
        if max(w, h) < config.MIN_IMAGE_EDGE:
            return None  # logo/ikon boyutunda -> atla
    except Exception:
        return None
    b = _img_to_b64(im, edge)
    if not b:
        return None
    digest = hashlib.md5(b.encode("ascii")).hexdigest()
    if digest in seen:
        return None  # ayni gorsel daha once alindi -> atla
    seen.add(digest)
    return b


def _pdf_images(path: Path, limit: int, progress: Callable = None, edge: int = None) -> list[str]:
    """Akilli: metinli sayfada gomulu gorsel, metinsiz sayfada sayfa goruntusu."""
    out: list[str] = []
    if fitz is None:
        return out
    try:
        doc = fitz.open(str(path))
    except Exception:
        return out
    seen: set = set()
    total = len(doc)
    try:
        for i, page in enumerate(doc):
            if progress and i % 2 == 0:
                progress("pdf", "PDF sayfaları işleniyor", i, total)
            if len(out) >= limit:
                break
            text = page.get_text().strip()
            if len(text) >= config.PAGE_TEXT_THRESHOLD:
                for img in page.get_images(full=True):
                    if len(out) >= limit:
                        break
                    try:
                        pix = fitz.Pixmap(doc, img[0])
                        if pix.n - pix.alpha >= 4:  # CMYK -> RGB
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        b = _filtered_b64(pix.tobytes("png"), seen, edge)
                        if b:
                            out.append(b)
                    except Exception:
                        continue
            else:
                try:
                    pix = page.get_pixmap(dpi=config.PDF_RENDER_DPI)
                    b = _bytes_to_b64(pix.tobytes("png"), edge)
                    if b:
                        out.append(b)
                except Exception:
                    continue
    finally:
        doc.close()
    return out


def _office_images(path: Path, ext: str, limit: int, progress: Callable = None, edge: int = None) -> list[str]:
    out: list[str] = []
    media = OFFICE_MEDIA_DIRS.get(ext)
    if not media:
        return out
    seen: set = set()
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.startswith(media)]
            total = len(names)
            for i, n in enumerate(names):
                if progress and i % 5 == 0:
                    progress("office", "Office medyaları ayıklanıyor", i, total)
                if len(out) >= limit:
                    break
                if Path(n).suffix.lower() not in IMAGE_EXTS:
                    continue
                b = _filtered_b64(z.read(n), seen, edge)
                if b:
                    out.append(b)
    except (zipfile.BadZipFile, OSError):
        pass
    return out


def _extract_text(path: Path, ext: str) -> str:
    if ext in TEXT_EXTS and ext not in (".html", ".htm"):
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    if _md is not None:
        try:
            return _md.convert(str(path)).text_content or ""
        except Exception:
            return ""
    return ""


def process_upload(username: str, chat_id: str, filename: str, raw: bytes, progress: Callable = None,
                   max_edge: int = None, max_images: int = None) -> dict:
    """Dosyayi sakla, metin + gorselleri cikar. Sonuc sozlugu dondurur."""
    if progress: progress("save", "Dosya diske kaydediliyor")
    ext = Path(filename).suffix.lower()
    fid = uuid.uuid4().hex
    base = config.USERS_DIR / username / "files" / chat_id / fid
    base.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(filename)
    stored = base / ("original_" + safe)
    stored.write_bytes(raw)

    # Vision modeli doğrudan görsel alıyorsa daha yüksek kenar + daha çok görsel.
    limit = max_images or config.MAX_IMAGES_PER_FILE
    edge = max_edge  # None ise helper'lar config.IMAGE_MAX_EDGE kullanir
    text = ""
    images_b64: list[str] = []

    if ext in IMAGE_EXTS:
        b = _bytes_to_b64(raw, edge)
        if b:
            images_b64 = [b]
    else:
        if progress: progress("text", "Metin içeriği ayıklanıyor")
        text = _extract_text(stored, ext)
        if ext == ".pdf":
            images_b64 = _pdf_images(stored, limit, progress, edge)
        elif ext in OFFICE_EXTS:
            images_b64 = _office_images(stored, ext, limit, progress, edge)

    if progress and len(images_b64) > 0:
        progress("images", "Görseller optimize ediliyor", 0, len(images_b64))

    images_b64 = images_b64[:limit]
    img_paths: list[str] = []
    for i, b in enumerate(images_b64):
        p = base / f"img_{i}.jpg"
        try:
            p.write_bytes(base64.b64decode(b))
            img_paths.append(str(p))
        except Exception:
            continue

    truncated = len(text) > config.MAX_FILE_TEXT_CHARS
    text = text[:config.MAX_FILE_TEXT_CHARS]

    return {
        "file_id": fid,
        "name": filename,
        "text": text,
        "truncated": truncated,
        "image_paths": img_paths,
        "num_images": len(img_paths),
        "stored_path": str(stored),
    }


def load_images_b64(paths: list[str]) -> list[str]:
    """Diskteki jpg gorselleri base64'e cevir (mesaj aninda modele gonderim icin)."""
    out: list[str] = []
    for p in paths:
        try:
            out.append(base64.b64encode(Path(p).read_bytes()).decode("ascii"))
        except OSError:
            continue
    return out


def available() -> dict:
    """Hangi cikarma yeteneklerinin yuklu oldugunu bildirir."""
    return {"markitdown": _md is not None, "pymupdf": fitz is not None, "pillow": Image is not None}
