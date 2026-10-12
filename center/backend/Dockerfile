# Build context is the repo root (see shared/infra/docker-compose.yml).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# Optional voice/face biometrics (heavy, UNTESTED path, off by default):
#   docker build --build-arg WITH_BIOMETRICS=1 ...
# installs ffmpeg and requirements-biometrics.txt (see that file: it targets Python 3.11/3.12 and
# needs face_recognition installed with --no-deps, so adjust the base image before enabling).
# At runtime also set BIOMETRICS_ENABLED=1 and DATA_KEY.
ARG WITH_BIOMETRICS=0

COPY shared/backend /srv/shared/backend
COPY center/backend/requirements.txt center/backend/requirements-biometrics.txt ./
RUN pip install --no-cache-dir -r requirements.txt ./shared/backend
RUN if [ "$WITH_BIOMETRICS" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/* \
      && pip install --no-cache-dir -r requirements-biometrics.txt \
      && pip install --no-cache-dir --no-deps face_recognition; \
    fi

COPY center/backend/app /srv/app

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5   CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# Only the gateway can reach this port (compose network), so trusting its
# X-Forwarded-For is safe and gives rate limiting the real client address.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
