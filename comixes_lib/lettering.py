"""Облачка поверх готового кадра. Текст в диффузию не идёт."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\comic.ttf"),
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)
TAILS = ("none", "bottom-left", "bottom-right", "top-left", "top-right")


def font(size: int, text: str = "") -> ImageFont.ImageFont:
    cyrillic = any("А" <= ch <= "я" or ch in "Ёё" for ch in text)
    order = (
        (
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path(r"C:\Windows\Fonts\comic.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        )
        if cyrillic
        else FONT_CANDIDATES
    )
    for path in order:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if draw.textlength(trial, font=face) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _foreground(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    height, width, _ = rgb.shape
    patches = [
        rgb[:20, :20],
        rgb[:20, width - 20 :],
        rgb[height - 20 :, :20],
        rgb[height - 20 :, width - 20 :],
    ]
    bg = np.median(np.concatenate([patch.reshape(-1, 3) for patch in patches], axis=0), axis=0)
    distance = np.linalg.norm(rgb - bg, axis=2)
    mask = distance > 26.0
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return mask
    out = np.zeros_like(mask)
    step = max(1, len(xs) // 5000)
    radius = max(10, min(width, height) // 70)
    for y, x in zip(ys[::step], xs[::step]):
        y0 = max(0, int(y) - radius)
        y1 = min(height, int(y) + radius + 1)
        x0 = max(0, int(x) - radius)
        x1 = min(width, int(x) + radius + 1)
        out[y0:y1, x0:x1] = True
    return out


def _measure(image: Image.Image, text: str) -> tuple[int, int, ImageFont.ImageFont, list[str], int]:
    width, height = image.size
    draw = ImageDraw.Draw(image)
    max_w = max(120, int(width * 0.34))
    font_size = max(16, min(34, width // 28))
    face = font(font_size, text)
    pad = 14
    lines = wrap(draw, text.strip(), face, max_w - pad * 2)
    while font_size > 15 and len(lines) * (font_size + 4) > int(height * 0.15):
        font_size -= 1
        face = font(font_size, text)
        lines = wrap(draw, text.strip(), face, max_w - pad * 2)
    line_h = font_size + 4
    text_w = max(int(draw.textlength(line, font=face)) for line in lines) if lines else 40
    box_w = min(max_w, text_w + pad * 2)
    box_h = min(int(height * 0.16), line_h * max(1, len(lines)) + pad * 2)
    return box_w, box_h, face, lines, pad


def _tail_toward(left: int, top: int, box_w: int, box_h: int, target_x: float, target_y: float) -> str:
    center_x = left + box_w / 2
    center_y = top + box_h / 2
    vertical = "bottom" if target_y >= center_y else "top"
    horizontal = "right" if target_x >= center_x else "left"
    return f"{vertical}-{horizontal}"


def _auto_box(image: Image.Image, text: str, blocked: list[tuple[int, int, int, int]] | None = None) -> tuple[int, int, int, int, str]:
    width, height = image.size
    box_w, box_h, _, _, _ = _measure(image, text)
    mask = _foreground(image)
    for x0, y0, x1, y1 in blocked or []:
        pad = 18
        mask[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = True
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        target = (width * 0.5, height * 0.55)
        face_box = None
    else:
        target = (float(xs.mean()), float(ys.mean()))
        band = int(height * 0.36)
        by, bx = np.nonzero(mask[:band])
        if len(bx):
            face_box = (int(bx.min()), int(by.min()), int(bx.max()), int(by.max()))
            target = ((face_box[0] + face_box[2]) / 2, (face_box[1] + face_box[3]) / 2)
        else:
            face_box = None

    best: tuple[float, int, int] | None = None
    stride = max(12, min(width, height) // 48)
    for top in range(6, max(7, height - box_h - 6), stride):
        for left in range(6, max(7, width - box_w - 6), stride):
            cover = float(mask[top : top + box_h, left : left + box_w].mean())
            face_penalty = 0.0
            if face_box is not None:
                fx0, fy0, fx1, fy1 = face_box
                ix0, iy0 = max(left, fx0), max(top, fy0)
                ix1, iy1 = min(left + box_w, fx1), min(top + box_h, fy1)
                if ix1 > ix0 and iy1 > iy0:
                    overlap = (ix1 - ix0) * (iy1 - iy0) / float(box_w * box_h)
                    face_penalty = overlap * 3.0
            upper_penalty = 0.04 * (top / height)
            blocked_penalty = 0.0
            for bx0, by0, bx1, by1 in blocked or []:
                ix0, iy0 = max(left, bx0), max(top, by0)
                ix1, iy1 = min(left + box_w, bx1), min(top + box_h, by1)
                if ix1 > ix0 and iy1 > iy0:
                    blocked_penalty += 12.0
            score = cover * 4.0 + face_penalty + upper_penalty + blocked_penalty
            if best is None or score < best[0]:
                best = (score, left, top)
    assert best is not None
    _, left, top = best
    tail = _tail_toward(left, top, box_w, box_h, target[0], target[1])
    return left, top, box_w, box_h, tail


def draw_bubble(
    base: Image.Image,
    text: str,
    x: float = 0.04,
    y: float = 0.03,
    w: float = 0.34,
    h: float = 0.14,
    tail: str = "bottom-left",
    placement: str = "auto",
    blocked: list[tuple[int, int, int, int]] | None = None,
) -> Image.Image:
    if not str(text).strip():
        return base
    width, height = base.size
    if placement == "auto":
        left, top, box_w, box_h, tail = _auto_box(base, text, blocked)
    else:
        box_w = max(48, int(width * w))
        box_h = max(36, int(height * h))
        left = int(np.clip(width * x, 0, max(0, width - box_w)))
        top = int(np.clip(height * y, 0, max(0, height - box_h)))
    outline = max(3, min(width, height) // 180)
    radius = max(12, int(min(box_w, box_h) * 0.28))
    canvas = base.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rect = [left, top, left + box_w, top + box_h]
    draw.rounded_rectangle(rect, radius=radius, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=outline)

    if tail != "none":
        if tail == "bottom-left":
            a = (left + box_w * 0.22, top + box_h - 1)
            b = (left + box_w * 0.46, top + box_h - 1)
            c = (left + box_w * 0.12, min(height - 2, top + box_h + box_h * 0.55))
        elif tail == "bottom-right":
            a = (left + box_w * 0.54, top + box_h - 1)
            b = (left + box_w * 0.78, top + box_h - 1)
            c = (left + box_w * 0.88, min(height - 2, top + box_h + box_h * 0.55))
        elif tail == "top-left":
            a = (left + box_w * 0.22, top + 1)
            b = (left + box_w * 0.46, top + 1)
            c = (left + box_w * 0.12, max(2, top - box_h * 0.55))
        else:
            a = (left + box_w * 0.54, top + 1)
            b = (left + box_w * 0.78, top + 1)
            c = (left + box_w * 0.88, max(2, top - box_h * 0.55))
        draw.polygon([a, b, c], fill=(255, 255, 255, 255))
        draw.line([a, c, b], fill=(0, 0, 0, 255), width=outline)
        draw.line([a, b], fill=(255, 255, 255, 255), width=outline + 2)

    _, _, face, lines, pad = _measure(base, text)
    if placement != "auto":
        font_size = max(14, int(box_h * 0.28))
        face = font(font_size, text)
        lines = wrap(draw, text.strip(), face, box_w - pad * 2)
        while font_size > 12 and len(lines) * (font_size + 4) > box_h - pad * 2:
            font_size -= 2
            face = font(font_size, text)
            lines = wrap(draw, text.strip(), face, box_w - pad * 2)
    line_h = (face.size if hasattr(face, "size") else 18) + 4
    block_h = line_h * max(1, len(lines))
    text_top = top + max(pad // 2, (box_h - block_h) // 2)
    for index, line in enumerate(lines):
        line_w = draw.textlength(line, font=face)
        draw.text((left + (box_w - line_w) / 2, text_top + index * line_h), line, fill=(0, 0, 0, 255), font=face)
    if blocked is not None:
        blocked.append((left, top, left + box_w, top + box_h))
    return Image.alpha_composite(canvas, overlay).convert("RGB")


def draw_sfx(image: Image.Image, text: str, x: float = 0.72, y: float = 0.22, scale: float = 0.16) -> Image.Image:
    raw = str(text).strip()
    if not raw:
        return image
    width, height = image.size
    size = max(28, int(min(width, height) * float(scale)))
    face = font(size, raw)
    canvas = image.convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    stroke = max(4, size // 10)
    anchor_x = int(width * float(x))
    anchor_y = int(height * float(y))
    text_w = draw.textlength(raw, font=face)
    left = int(np.clip(anchor_x - text_w / 2, 8, max(8, width - text_w - 8)))
    top = int(np.clip(anchor_y, 8, max(8, height - size - 8)))
    draw.text((left, top), raw, font=face, fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    return canvas.convert("RGB")


def draw_bubbles(image: Image.Image, bubbles: list[tuple]) -> Image.Image:
    result = image
    blocked: list[tuple[int, int, int, int]] = []
    for text, x, y, w, h, tail, placement in bubbles:
        result = draw_bubble(result, text, x, y, w, h, tail, placement, blocked)
    return result
