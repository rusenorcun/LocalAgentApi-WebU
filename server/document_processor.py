"""KALDIRILDI (M2/K1) — ölü ve bozuk modüldü.

Bu modül hiçbir yerden import edilmiyordu ve `_bytes_to_b64`'ü import etmeden
kullandığı için çağrılsa NameError verirdi. Tek dosya işleme hattı
`files.process_upload`'dur; RAG tarafı için `routers.rag._process_document`
kullanılır. Yanlışlıkla import edilirse açık hata versin diye stub bırakıldı.
"""


def process_file(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError(
        "document_processor.process_file kaldırıldı — files.process_upload kullanın."
    )
