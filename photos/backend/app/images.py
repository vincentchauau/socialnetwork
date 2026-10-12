"""Content-based image validation and re-encoding (strips EXIF and other metadata)."""

import io
import threading
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_SOURCE_PIXELS = 16_000_000  # refuse decompression bombs before decoding
MAX_CONCURRENT_PROCESSING = 2
SLOT_TIMEOUT_SECONDS = 2.0
_slots = threading.BoundedSemaphore(MAX_CONCURRENT_PROCESSING)
THUMB_DIMENSION = 400
JPEG_QUALITY = 88
THUMB_QUALITY = 80

# Pillow format name -> (content type, file extension)
ALLOWED_FORMATS: dict[str, tuple[str, str]] = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
    "GIF": ("image/gif", "gif"),
}
THUMB_CONTENT_TYPE = "image/webp"
THUMB_EXTENSION = "webp"


class InvalidImageError(ValueError):
    """The upload is not an acceptable image."""


class ImageBusyError(RuntimeError):
    """No processing slot became free in time."""


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    content_type: str
    extension: str
    width: int
    height: int
    thumb_data: bytes


def _encode(image: Image.Image, fmt: str, **options: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def _clean_copy(image: Image.Image, fmt: str) -> Image.Image:
    """A metadata-free copy in a mode the target format can store."""
    if fmt == "JPEG":
        return image.convert("RGB")
    if fmt == "GIF":
        return image.convert("P", palette=Image.Palette.ADAPTIVE)
    return image.convert("RGBA" if image.has_transparency_data else "RGB")


def process_image(raw: bytes) -> ProcessedImage:
    """Validate by decoding, then re-encode full size and thumbnail.

    Raises InvalidImageError, or ImageBusyError when too many images are being processed.
    """
    if not raw:
        raise InvalidImageError("The file is empty")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise InvalidImageError("The file is larger than 5 MB")
    if not _slots.acquire(timeout=SLOT_TIMEOUT_SECONDS):
        raise ImageBusyError("The server is busy processing images, try again shortly")
    try:
        return _process(raw)
    finally:
        _slots.release()


def _process(raw: bytes) -> ProcessedImage:
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            fmt = opened.format or ""
            if fmt not in ALLOWED_FORMATS:
                raise InvalidImageError("Only JPEG, PNG, WebP and GIF images are accepted")
            if opened.width * opened.height > MAX_SOURCE_PIXELS:
                raise InvalidImageError("The image is too large")
            opened.seek(0)  # animated formats: keep the first frame only
            if fmt == "JPEG":
                opened.draft("RGB", (MAX_DIMENSION, MAX_DIMENSION))  # decode at reduced scale
            oriented = ImageOps.exif_transpose(opened)
            oriented.load()
            return _build(oriented, fmt)
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise InvalidImageError("The file is not a valid image") from None


def _thumbnail_of(full: Image.Image) -> Image.Image:
    """WebP-storable thumbnail derived from the already-downscaled image."""
    if full.mode in ("RGB", "RGBA"):
        thumb = full.copy()
    else:
        thumb = full.convert("RGBA" if full.has_transparency_data else "RGB")
    thumb.thumbnail((THUMB_DIMENSION, THUMB_DIMENSION))
    return thumb


def _build(image: Image.Image, fmt: str) -> ProcessedImage:
    full = _clean_copy(image, fmt)
    full.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    thumb = _thumbnail_of(full)
    options = {"quality": JPEG_QUALITY} if fmt in ("JPEG", "WEBP") else {}
    content_type, extension = ALLOWED_FORMATS[fmt]
    return ProcessedImage(
        data=_encode(full, fmt, **options),
        content_type=content_type,
        extension=extension,
        width=full.width,
        height=full.height,
        thumb_data=_encode(thumb, "WEBP", quality=THUMB_QUALITY),
    )
