# Build context is the repo root (see shared/infra/docker-compose.yml).
# Python 3.12: the optional face/voice libraries (resemblyzer, dlib) do not support 3.13 yet.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# Voice + face sign-in is optional and heavy (torch, dlib, opencv, ffmpeg). Build with
#   WITH_BIOMETRICS=1  (set it in .env; compose passes it as a build arg)
# and enable it at runtime with BIOMETRICS_ENABLED=1 and a DATA_KEY (see .env.example).
ARG WITH_BIOMETRICS=0

COPY shared/backend /srv/shared/backend
COPY center/backend/requirements.txt center/backend/requirements-biometrics.txt ./
RUN pip install --no-cache-dir -r requirements.txt ./shared/backend

# build-essential is only needed to compile webrtcvad (a resemblyzer dependency) and is removed again.
# torch comes from the CPU-only index: the default Linux wheel bundles ~2 GB of CUDA libraries.
RUN if [ "$WITH_BIOMETRICS" = "1" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends ffmpeg build-essential \
      && pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu "torch" \
      && pip install --no-cache-dir -r requirements-biometrics.txt \
      && pip install --no-cache-dir --no-deps face_recognition \
      && apt-get purge -y build-essential && apt-get autoremove -y \
      && rm -rf /var/lib/apt/lists/*; \
    fi

# librosa/numba compile and cache machine code on first use (~45 s, longer than a web request may
# wait). Compile once at build time into a cache the unprivileged app user can read and extend.
# HOME/MPLCONFIGDIR point at /tmp because the app user has no home directory.
ENV NUMBA_CACHE_DIR=/opt/numba-cache MPLCONFIGDIR=/tmp/matplotlib HOME=/tmp
RUN if [ "$WITH_BIOMETRICS" = "1" ]; then \
      mkdir -p "$NUMBA_CACHE_DIR" \
      && python -c "import numpy as np; from resemblyzer import VoiceEncoder; VoiceEncoder('cpu').embed_utterance((np.random.randn(48000) * 0.1).astype(np.float32))" \
      && chown -R 10001 "$NUMBA_CACHE_DIR"; \
    fi

COPY center/backend/app /srv/app

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5   CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# Only the gateway can reach this port (compose network), so trusting its
# X-Forwarded-For is safe and gives rate limiting the real client address.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
