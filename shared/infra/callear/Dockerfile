# The ear of the calls: joins the call of a room as a hidden listener, hears each person who speaks in it, and hands what was said to the chat
# (which makes it into words and writes it as that person's message). It holds no model and no key of the platform: only the key to join rooms.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir livekit==1.1.21 fastapi==0.115.6 "uvicorn[standard]==0.34.0" httpx==0.28.1
COPY app.py ./
RUN useradd --no-create-home --shell /usr/sbin/nologin ear
USER ear
EXPOSE 8200
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
