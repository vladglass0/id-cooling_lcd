"""Theme model + PIL renderer (vendor .mPanelTheme equivalent, our format).

Theme dict:
  {"background": {"type": "color", "color": [r,g,b]}
                  | {"type": "image", "path": "..."},
   "widgets": [{"id": str, "type": "cpu_temp|gpu_temp|cpu_load|time|text|bar",
                "x": int, "y": int,            # anchor position, 240-space
                "size": int,                   # font size or bar height
                "color": [r,g,b],
                "text": str,                   # text/bar label
                "w": int,                      # bar width (bar only)
                "source": str}]                # bar value source (bar only)
  }
Text widgets anchor top-center at (x, y). Bars anchor top-left.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import rlcd15
from image_pipe import _font, encode_jpeg

BAR_SOURCES = ("cpu_temp", "cpu_load", "gpu_temp")


def default_theme() -> dict:
    return {
        "background": {"type": "color", "color": [0, 0, 0]},
        "widgets": [
            {"id": "w_cpu_lbl", "type": "text", "x": 120, "y": 22,
             "size": 30, "color": [255, 80, 64], "text": "CPU"},
            {"id": "w_cpu", "type": "cpu_temp", "x": 120, "y": 118,
             "size": 88, "color": [255, 255, 255], "text": ""},
            {"id": "w_gpu", "type": "gpu_temp", "x": 120, "y": 206,
             "size": 26, "color": [255, 80, 64], "text": ""},
        ],
    }


def _fmt_temp(v):
    return f"{v:.0f}\u00b0" if v is not None else "--"


def render(theme: dict, values: dict):
    """Render theme to PIL image. Returns (image, rects for hit-testing)."""
    bg = theme.get("background", {"type": "color", "color": [0, 0, 0]})
    if bg.get("type") == "image" and bg.get("path"):
        try:
            img = Image.open(bg["path"]).convert("RGB")
            w, h = img.size
            side = min(w, h)
            img = img.crop(((w - side) // 2, (h - side) // 2,
                            (w + side) // 2, (h + side) // 2))
            img = img.resize((rlcd15.WIDTH, rlcd15.HEIGHT), Image.LANCZOS)
        except (OSError, ValueError):
            img = Image.new("RGB", (rlcd15.WIDTH, rlcd15.HEIGHT), (0, 0, 0))
    else:
        img = Image.new("RGB", (rlcd15.WIDTH, rlcd15.HEIGHT),
                        tuple(bg.get("color", [0, 0, 0])))
    d = ImageDraw.Draw(img)
    rects = []
    for wdg in theme.get("widgets", []):
        color = tuple(wdg.get("color", [255, 255, 255]))
        size = max(1, int(wdg.get("size", 28)))  # never 0 (PIL rejects it)
        x, y = int(wdg.get("x", 120)), int(wdg.get("y", 120))
        t = wdg.get("type")
        if t == "cpu_temp":
            txt = _fmt_temp(values.get("cpu_c"))
        elif t == "gpu_temp":
            txt = f"GPU {_fmt_temp(values.get('gpu_c'))}"
        elif t == "cpu_load":
            v = values.get("cpu_load")
            txt = f"CPU {v:.0f}%" if v is not None else "CPU --"
        elif t == "time":
            txt = values.get("time_str", "--:--")
        elif t == "bar":
            src = wdg.get("source", "cpu_temp")
            v = values.get({"cpu_temp": "cpu_c"}.get(src, src))
            frac = 0.0 if v is None else min(1.0, max(0.0, v / 100.0))
            bw, bh = max(1, int(wdg.get("w", 200))), size
            d.rectangle([x, y, x + bw, y + bh], fill=(40, 40, 48))
            d.rectangle([x, y, x + int(bw * frac), y + bh], fill=color)
            rects.append((wdg["id"], x, y, bw, bh))
            continue
        else:  # text
            txt = wdg.get("text", "")
        font = _font(size)
        d.text((x, y), txt, font=font, fill=color, anchor="ma")
        l, t_, r, b = d.textbbox((x, y), txt, font=font, anchor="ma")
        rects.append((wdg["id"], l, t_, r - l, b - t_))
    return img, rects


def to_jpeg(theme: dict, values: dict) -> bytes:
    img, _ = render(theme, values)
    return encode_jpeg(img)
