FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEMO_MODE=false \
    COOKIE_SECURE=true \
    WHATSAPP_ENABLED=false \
    COURTLOG_DB_PATH=/var/lib/courtlog/courtlog.sqlite3 \
    JWT_PRIVATE_KEY_PATH=/var/lib/courtlog/private.pem \
    JWT_PUBLIC_KEY_PATH=/var/lib/courtlog/public.pem

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

RUN groupadd --system courtlog \
    && useradd --system --gid courtlog --home-dir /nonexistent --shell /usr/sbin/nologin courtlog \
    && mkdir -p /var/lib/courtlog \
    && chown -R courtlog:courtlog /var/lib/courtlog /app

USER courtlog:courtlog

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/config', timeout=3).read()"]

CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
