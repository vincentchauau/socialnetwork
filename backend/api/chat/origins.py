import os

DEFAULT_ALLOWED_ORIGINS = "http://localhost:8080"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def allowed_origins() -> set[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return {origin.strip() for origin in raw.split(",") if origin.strip()}
