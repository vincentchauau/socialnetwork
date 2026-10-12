# Build context is the repo root (see shared/infra/docker-compose.yml).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY shared/backend /srv/shared/backend
COPY market/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt ./shared/backend

COPY market/backend/app /srv/app

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5   CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# Only the gateway can reach this port (compose network), so trusting its
# X-Forwarded-For is safe and gives rate limiting the real client address.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
