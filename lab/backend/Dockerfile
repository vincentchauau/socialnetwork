# Build context is the repo root (see shared/infra/docker-compose.yml).
# One image, three commands: lab-backend (uvicorn, the default CMD), lab-user (python -m app.user_server)
# and lab-worker (python -m app.worker).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY shared/backend /srv/shared/backend
COPY lab/backend/requirements.txt .
# grpcio-tools is installed only to generate the stubs below (same resolve as grpcio, so versions match).
RUN pip install --no-cache-dir -r requirements.txt ./shared/backend grpcio-tools

COPY lab/backend/app /srv/app
RUN python -m grpc_tools.protoc -Iapp/proto --python_out=app/proto --grpc_python_out=app/proto app/proto/user.proto \
    && pip uninstall -y grpcio-tools

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5   CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# Only the gateway can reach this port (compose network), so trusting its
# X-Forwarded-For is safe and gives rate limiting the real client address.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
