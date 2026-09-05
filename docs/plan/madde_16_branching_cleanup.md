# Madde 16 — Dallanma + Dosya Temizliği + V1 Ölü Kod

## #3 — V1 compact_if_needed / ölü uçlar (DÜŞÜK RİSK)
- Tespit: Frontend yalnız `/api/v2/*` kullanıyor. main.py'deki V1 sohbet uçları
  (`/api/chats` CRUD, `/api/chats/{id}/message`, `/api/chats/{id}/upload`) ölü;
  `compact_if_needed` JSON'a yazar → karışıklık riski.
- Çözüm: V1 sohbet uçlarını (CRUD + message + upload) main.py'den kaldır. Auth/models/
  admin/health/SPA kalır. Böylece JSON/SQLite çakışma yüzeyi yok olur.

## #2 — Dangling files (ORTA RİSK)
- Tespit: `delete_document` (rag.py) ve `delete_chat` (chats.py) yalnız DB satırını siler.
  Dosyalar: RAG `data/rag_uploads/<uid>/<ad>`; sohbet `users/<user>/files/<chat_id>/...`.
- Çözüm:
  - `delete_document`: `doc.path` dosyasını sil; boşsa klasörü temizle.
  - `delete_chat`: `USERS_DIR/<username>/files/<chat_id>/` dizinini sil.
  - Ek güvence: `Document` için SQLAlchemy `after_delete` event (path tabanlı, kendi içinde).

## #1 — Dallanma (Branching) — YÜKSEK İŞ
Mesaj silme yerine ağaç yapısı (ChatGPT/Claude gibi).

### Şema
- `Message.parent_id` (FK messages.id, null) — ağaç ebeveyni.
- `Message.active` (bool, default True) — KARDEŞLER arasında seçili olan (yerel işaretçi).
- Aktif yol: aktif kökten başla, her düğümde aktif çocuğa in → yaprağa kadar.
- Migrasyon + backfill: mevcut lineer sohbetleri zincire çevir (parent_id = önceki mesaj).

### Mantık (yardımcılar)
- `_active_path(msgs)`: aktif yolu yürür (kök→yaprak).
- `_sibling_meta(msgs)`: her mesaj için {parent_id, index, count}.
- Üretim penceresi + kompaktlama = aktif yol (gizli mesajlar dahil; UI'da gizliler elenir).

### Uçlar
- `send_message`: yeni user mesajı parent = aktif yaprak. `edit_message_id` verilirse:
  düzenlenen mesajın ALT AĞACINI pasifleştir, aynı parent altında YENİ kardeş user
  mesajı (active) oluştur, altına yanıt üret → eski dal korunur.
- `regenerate`: asistan mesajının kardeşi olarak yeni yanıt (eski pasif).
- `select-branch` (yeni): bir kardeşi aktifleştir (diğer kardeşleri pasifleştir).
- `truncate`: artık edit akışında KULLANILMAZ (dallanma onun yerine); uç dursa da UI çağırmaz.

### API çıktısı
- `_chat_to_dict`: yalnız AKTİF YOL mesajları (UI'da gizliler hariç) + her mesaja
  `parent_id`, `branch_index`, `branch_count`.

### UI
- MessageBubble: kardeş>1 ise "‹ i/n ›" navigasyonu → `select-branch`.
- Edit: `truncateChat` yerine `edit_message_id` ile gönder (dal aç).

### Doğrulama
- Backfill mevcut sohbetleri bozmadan zincire çevirir.
- Edit → eski dal DB'de durur, aktif yol yeni; switch ile geri dönülebilir.
- Üretim yalnız aktif yolu görür. tsc 0, py_compile, init_db head.
