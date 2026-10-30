# syntax=docker/dockerfile:1
# Single image serving the API, the built SPA (same origin) and the background worker.

FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 tandem
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=frontend /build/dist /app/frontend/dist
RUN mkdir -p /app/backend/var/storage /data/storage && chown -R tandem:tandem /app /data/storage
USER tandem
ENV FRONTEND_DIST=/app/frontend/dist FLASK_APP=app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "app:create_app()"]
