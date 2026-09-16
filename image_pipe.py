"""Host-side frame rendering for RLCD_1_5 (240x240).

The pump only decodes baseline JPEGs; all composition happens here with
Pillow (same approach as the vendor app, which renders via Qt/ffmpeg).
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import rlcd15

JPEG_QUALITY = 92  # vendor frames decode to ~1.5 KB at 240x240

_FONT_CANDIDATES = [
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def encode_jpeg(img: Image.Image, quality: int = JPEG_QUALITY) -> bytes:
    """Encode a 240x240 RGB image as baseline JPEG.

    The pump panel is mounted rotated 180° (vendor app rotates too),
    so flip here — preview of these bytes stays WYSIWYG.
    """
    assert img.size == (rlcd15.WIDTH, rlcd15.HEIGHT), img.size
    buf = io.BytesIO()
    img.convert("RGB").transpose(Image.ROTATE_180).save(
        buf, "JPEG", quality=quality, optimize=False, progressive=False)
    return buf.getvalue()


def solid(color: tuple) -> bytes:
    """Solid-color frame (e.g. calibration), returns JPEG bytes."""
    return encode_jpeg(Image.new("RGB", (rlcd15.WIDTH, rlcd15.HEIGHT), color))


def temp_card(cpu_c: float, gpu_c: float | None = None,
              bg: tuple = (0, 0, 0), fg: tuple = (255, 255, 255),
              accent: tuple = (255, 60, 40)) -> bytes:
    """Monitoring card: big CPU temp + smaller GPU temp, 240x240."""
    img = Image.new("RGB", (rlcd15.WIDTH, rlcd15.HEIGHT), bg)
    d = ImageDraw.Draw(img)
    d.text((120, 22), "CPU", font=_font(30), fill=accent, anchor="ma")
    d.text((120, 118), f"{cpu_c:.0f}\u00b0", font=_font(88), fill=fg,
           anchor="ma")
    if gpu_c is None:
        label = "--"
    else:
        label = f"GPU {gpu_c:.0f}\u00b0"
    d.text((120, 206), label, font=_font(26), fill=accent, anchor="ma")
    return encode_jpeg(img)


def from_file(path: str | Path) -> bytes:
    """Any image file → square-cropped 240x240 JPEG."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2,
                    (w + side) // 2, (h + side) // 2))
    return encode_jpeg(img.resize((rlcd15.WIDTH, rlcd15.HEIGHT), Image.LANCZOS))


def gif_frames(path: str | Path, max_frames: int = 60) -> list:
    """GIF → list of 240x240 JPEG frames (one DRA upload each)."""
    img = Image.open(path)
    out = []
    i = 0
    try:
        while i < max_frames:
            out.append(encode_jpeg(
                img.convert("RGB").resize(
                    (rlcd15.WIDTH, rlcd15.HEIGHT), Image.LANCZOS)))
            i += 1
            img.seek(i)
    except EOFError:
        pass
    return out
