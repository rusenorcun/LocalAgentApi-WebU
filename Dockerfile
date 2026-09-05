# ── Aşama 1: React Arayüzünü Derle ──────────────────────────────────────────
FROM node:20-alpine AS web-builder

WORKDIR /app/web

COPY web/package*.json ./
RUN npm ci || npm install

COPY web/ ./
RUN npm run build

# ── Aşama 2: Python FastAPI Sunucusu ────────────────────────────────────────
FROM python:3.11-slim AS runner

WORKDIR /app

# Gerekli sistem kütüphaneleri (PyMuPDF, Pillow ve sağlık kontrolleri için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Bağımlılıkları kur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodlarını ve veritabanı ayarlarını kopyala
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY server/ ./server/

# MCP HTTP relay (admin panelinden başlatılan alt süreç, bkz.
# server/services/mcp_manager.py). Docker'da docker-compose.yml içindeki
# volume mount bu klasörün üzerine host'unkini bindler ki .mcp_token
# kalıcı kalsın; bu COPY yalnızca compose'suz/tek başına `docker run`
# senaryosunda dosyaların image içinde de bulunmasını garantiler.
COPY mcp/ ./mcp/

# Aşama 1'de derlenen frontend SPA çıktısını kopyala
COPY --from=web-builder /app/web/dist ./web/dist

# Veri klasörü
RUN mkdir -p /app/data

ENV HOST=0.0.0.0
ENV PORT=9000
ENV DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

EXPOSE 9000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:9000/api/v2/health || exit 1

CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "9000"]
