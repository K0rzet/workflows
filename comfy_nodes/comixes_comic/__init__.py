"""Ноды комикса: модель, персонаж, облачко, страница, опциональная LoRA."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(os.environ.get("COMIXES_PROJECT", Path(__file__).resolve().parents[2])).resolve()
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from comixes_lib.prompting import assert_allowed, build_prompts, dataset_caption, load_card
from comixes_lib.paths import CHECKPOINT_NAMES, COMFY_INPUT, DATASETS, PYTHON, VAE

import comfy.sd
import comfy.utils
import folder_paths
from nodes import CLIPSetLastLayer, CheckpointLoaderSimple, VAELoader

FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\comic.ttf"),
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
)
TAILS = ["none", "bottom-left", "bottom-right", "top-left", "top-right"]


def _font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _tensor_to_pil(image: torch.Tensor) -> Image.Image:
    frame = image[0] if image.dim() == 4 else image
    array = (frame.detach().clamp(0, 1).cpu().numpy() * 255.0).astype(np.uint8)
    return Image.fromarray(array[..., :3], mode="RGB")


def _pil_to_tensor(image: Image.Image) -> torch.Tensor:
    array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _draw_bubble(base: Image.Image, text: str, x: float, y: float, w: float, h: float, tail: str) -> Image.Image:
    if not text.strip():
        return base
    width, height = base.size
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
            a = (left + box_w * 0.18, top + box_h - 1)
            b = (left + box_w * 0.42, top + box_h - 1)
            c = (left + box_w * 0.08, min(height - 2, top + box_h + box_h * 0.42))
        elif tail == "bottom-right":
            a = (left + box_w * 0.58, top + box_h - 1)
            b = (left + box_w * 0.82, top + box_h - 1)
            c = (left + box_w * 0.92, min(height - 2, top + box_h + box_h * 0.42))
        elif tail == "top-left":
            a = (left + box_w * 0.18, top + 1)
            b = (left + box_w * 0.42, top + 1)
            c = (left + box_w * 0.08, max(2, top - box_h * 0.42))
        else:
            a = (left + box_w * 0.58, top + 1)
            b = (left + box_w * 0.82, top + 1)
            c = (left + box_w * 0.92, max(2, top - box_h * 0.42))
        draw.polygon([a, b, c], fill=(255, 255, 255, 255))
        draw.line([a, c, b], fill=(0, 0, 0, 255), width=outline)
        draw.line([a, b], fill=(255, 255, 255, 255), width=outline + 2)

    pad = outline + 8
    font_size = max(14, int(box_h * 0.28))
    font = _font(font_size)
    lines = _wrap(draw, text.strip(), font, box_w - pad * 2)
    while font_size > 12 and len(lines) * (font_size + 4) > box_h - pad * 2:
        font_size -= 2
        font = _font(font_size)
        lines = _wrap(draw, text.strip(), font, box_w - pad * 2)
    line_h = font_size + 4
    block_h = line_h * max(1, len(lines))
    text_top = top + max(pad, (box_h - block_h) // 2)
    for index, line in enumerate(lines):
        line_w = draw.textlength(line, font=font)
        draw.text((left + (box_w - line_w) / 2, text_top + index * line_h), line, fill=(0, 0, 0, 255), font=font)
    return Image.alpha_composite(canvas, overlay).convert("RGB")


class ComixesLoadFamily:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model_family": (list(CHECKPOINT_NAMES),)}}

    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "STRING")
    RETURN_NAMES = ("model", "clip", "vae", "model_family")
    FUNCTION = "load"
    CATEGORY = "comixes"

    def load(self, model_family):
        checkpoint = CHECKPOINT_NAMES[model_family]
        model, clip, checkpoint_vae = CheckpointLoaderSimple().load_checkpoint(checkpoint)
        vae_name = VAE.name
        vae = (VAELoader().load_vae(vae_name)[0]
               if vae_name in folder_paths.get_filename_list("vae") else checkpoint_vae)
        clip = CLIPSetLastLayer().set_last_layer(clip, -2)[0]
        return (model, clip, vae, model_family)


class ComixesCharacterPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "character": ("STRING", {"default": "kira.json"}),
                "model_family": ("STRING", {"default": "wai"}),
                "rating": (["rating_explicit", "rating_questionable", "rating_safe"],),
                "scene": ("STRING", {"multiline": True, "default": "standing, full body, looking at viewer"}),
                "solo": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "style_preset": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("positive", "negative", "lora_name", "strength_model", "strength_clip", "scene")
    FUNCTION = "build"
    CATEGORY = "comixes"

    def build(self, character, model_family, rating, scene, solo=True, style_preset=""):
        try:
            card = load_card(character)
            if str(style_preset).strip():
                card["style"] = ""
                card["style_preset"] = str(style_preset).strip()
            positive, negative = build_prompts(card, scene, rating, model_family, solo=bool(solo))
        except (ValueError, FileNotFoundError) as exc:
            raise RuntimeError(str(exc)) from exc
        lora_name = str(card.get("lora") or "none").strip() or "none"
        return (
            positive,
            negative,
            lora_name,
            float(card.get("lora_strength_model", 0.85)),
            float(card.get("lora_strength_clip", 0.75)),
            scene,
        )


class ComixesGuardText:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": ("STRING", {"multiline": True, "default": ""})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "guard"
    CATEGORY = "comixes"

    def guard(self, text):
        try:
            assert_allowed(text)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        return (text,)


class ComixesOptionalLora:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "lora_name": ("STRING", {"default": "none"}),
                "strength_model": ("FLOAT", {"default": 0.85, "min": -2.0, "max": 2.0, "step": 0.01}),
                "strength_clip": ("FLOAT", {"default": 0.75, "min": -2.0, "max": 2.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP")
    FUNCTION = "apply"
    CATEGORY = "comixes"

    def apply(self, model, clip, lora_name, strength_model, strength_clip):
        name = (lora_name or "").strip()
        if name.lower() in {"", "none", "null"} or (strength_model == 0 and strength_clip == 0):
            return (model, clip)
        available = folder_paths.get_filename_list("loras")
        match = next((item for item in available if item.replace("\\", "/") == name.replace("\\", "/") or item.endswith(name)), None)
        if match is None:
            print(f"[comixes] LoRA «{name}» ещё нет, генерация идёт без неё.")
            return (model, clip)
        lora_path = folder_paths.get_full_path_or_raise("loras", match)
        lora, metadata = comfy.utils.load_torch_file(lora_path, safe_load=True, return_metadata=True)
        model_lora, clip_lora = comfy.sd.load_lora_for_models(
            model, clip, lora, strength_model, strength_clip, lora_metadata=metadata
        )
        return (model_lora, clip_lora)


class ComixesSpeechBubble:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "text_1": ("STRING", {"multiline": True, "default": ""}),
                "x_1": ("FLOAT", {"default": 0.52, "min": 0.0, "max": 1.0, "step": 0.01}),
                "y_1": ("FLOAT", {"default": 0.03, "min": 0.0, "max": 1.0, "step": 0.01}),
                "w_1": ("FLOAT", {"default": 0.42, "min": 0.05, "max": 1.0, "step": 0.01}),
                "h_1": ("FLOAT", {"default": 0.20, "min": 0.05, "max": 1.0, "step": 0.01}),
                "tail_1": (TAILS, {"default": "bottom-left"}),
                "text_2": ("STRING", {"multiline": True, "default": ""}),
                "x_2": ("FLOAT", {"default": 0.06, "min": 0.0, "max": 1.0, "step": 0.01}),
                "y_2": ("FLOAT", {"default": 0.68, "min": 0.0, "max": 1.0, "step": 0.01}),
                "w_2": ("FLOAT", {"default": 0.40, "min": 0.05, "max": 1.0, "step": 0.01}),
                "h_2": ("FLOAT", {"default": 0.18, "min": 0.05, "max": 1.0, "step": 0.01}),
                "tail_2": (TAILS, {"default": "top-right"}),
                "text_3": ("STRING", {"multiline": True, "default": ""}),
                "x_3": ("FLOAT", {"default": 0.30, "min": 0.0, "max": 1.0, "step": 0.01}),
                "y_3": ("FLOAT", {"default": 0.40, "min": 0.0, "max": 1.0, "step": 0.01}),
                "w_3": ("FLOAT", {"default": 0.35, "min": 0.05, "max": 1.0, "step": 0.01}),
                "h_3": ("FLOAT", {"default": 0.16, "min": 0.05, "max": 1.0, "step": 0.01}),
                "tail_3": (TAILS, {"default": "none"}),
            },
            "optional": {
                "placement_1": (["auto", "manual"], {"default": "auto"}),
                "placement_2": (["auto", "manual"], {"default": "auto"}),
                "placement_3": (["auto", "manual"], {"default": "auto"}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "draw"
    CATEGORY = "comixes"

    def draw(
        self,
        image,
        text_1, x_1, y_1, w_1, h_1, tail_1,
        text_2, x_2, y_2, w_2, h_2, tail_2,
        text_3, x_3, y_3, w_3, h_3, tail_3,
        placement_1="auto",
        placement_2="auto",
        placement_3="auto",
    ):
        from comixes_lib.lettering import draw_bubbles

        bubbles = (
            (text_1, x_1, y_1, w_1, h_1, tail_1, placement_1),
            (text_2, x_2, y_2, w_2, h_2, tail_2, placement_2),
            (text_3, x_3, y_3, w_3, h_3, tail_3, placement_3),
        )
        frames = []
        for index in range(image.shape[0]):
            pil = _tensor_to_pil(image[index:index + 1])
            frames.append(_pil_to_tensor(draw_bubbles(pil, bubbles)))
        return (torch.cat(frames, dim=0),)


class ComixesFitLongSide:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "long_side": ("INT", {"default": 1216, "min": 256, "max": 2048, "step": 8}),
            },
            "optional": {"mask": ("MASK",)},
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "fit"
    CATEGORY = "comixes"

    def fit(self, image, long_side, mask=None):
        _, height, width, _ = image.shape
        scale = long_side / max(height, width)
        new_h = max(64, int(round(height * scale / 8.0)) * 8)
        new_w = max(64, int(round(width * scale / 8.0)) * 8)
        if (new_h, new_w) != (height, width):
            pixels = comfy.utils.common_upscale(image.movedim(-1, 1), new_w, new_h, "lanczos", "disabled")
            image = pixels.movedim(1, -1)
        if mask is None:
            mask = torch.zeros((image.shape[0], new_h, new_w), dtype=image.dtype, device=image.device)
        else:
            if mask.dim() == 2:
                mask = mask.unsqueeze(0)
            mask_bchw = comfy.utils.common_upscale(mask.unsqueeze(1), new_w, new_h, "nearest-exact", "disabled")
            mask = mask_bchw.squeeze(1)
        return (image, mask)


class ComixesFitCanvas:
    """Fit an image onto an exact canvas without changing its geometry.

    Qwen Image 2.1 derives the sampling latent size from its first reference.
    A normal ImageScale with ``crop=disabled`` stretches that reference to the
    requested panel ratio.  This node instead performs a proportional resize
    and centres the result on a neutral canvas, so the first reference can set
    the target latent size without distorting faces or bodies.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "width": ("INT", {"default": 1024, "min": 32, "max": 8192, "step": 1}),
                "height": ("INT", {"default": 1024, "min": 32, "max": 8192, "step": 1}),
                "background": (["neutral gray", "white", "black"], {"default": "neutral gray"}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "fit"
    CATEGORY = "comixes"

    def fit(self, image, width, height, background="neutral gray"):
        batch, source_h, source_w, channels = image.shape
        scale = min(width / source_w, height / source_h)
        fitted_w = max(1, min(width, int(round(source_w * scale))))
        fitted_h = max(1, min(height, int(round(source_h * scale))))
        if (fitted_h, fitted_w) == (source_h, source_w):
            fitted = image
        else:
            fitted = comfy.utils.common_upscale(
                image.movedim(-1, 1), fitted_w, fitted_h, "lanczos", "disabled"
            ).movedim(1, -1)
        fill = {"neutral gray": 0.5, "white": 1.0, "black": 0.0}[background]
        canvas = torch.full(
            (batch, height, width, channels), fill,
            dtype=image.dtype, device=image.device,
        )
        if channels > 3:
            canvas[..., 3:] = 0.0
        top = (height - fitted_h) // 2
        left = (width - fitted_w) // 2
        canvas[:, top:top + fitted_h, left:left + fitted_w, :] = fitted
        return (canvas,)


class ComixesPage:
    @classmethod
    def INPUT_TYPES(cls):
        optional = {f"panel_{index}": ("IMAGE",) for index in range(1, 7)}
        return {
            "required": {
                "columns": ("INT", {"default": 2, "min": 1, "max": 3, "step": 1}),
                "gutter": ("INT", {"default": 18, "min": 0, "max": 200, "step": 1}),
                "margin": ("INT", {"default": 28, "min": 0, "max": 300, "step": 1}),
                "border": ("INT", {"default": 8, "min": 0, "max": 64, "step": 1}),
            },
            "optional": {"layout": (["grid", "wide_top"], {"default": "grid"}), **optional},
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "compose"
    CATEGORY = "comixes"

    def compose(self, columns, gutter, margin, border, layout="grid", **panels):
        images = []
        for index in range(1, 7):
            panel = panels.get(f"panel_{index}")
            if panel is not None:
                images.append(_tensor_to_pil(panel))
        if not images:
            return (_pil_to_tensor(Image.new("RGB", (512, 512), "white")),)
        if layout == "wide_top" and len(images) >= 2:
            return (_pil_to_tensor(_page_wide_top(images, columns, gutter, margin, border)),)
        cell_w = max(image.width for image in images)
        cell_h = max(image.height for image in images)
        columns = max(1, min(columns, len(images)))
        rows = (len(images) + columns - 1) // columns
        page_w = margin * 2 + columns * cell_w + (columns - 1) * gutter
        page_h = margin * 2 + rows * cell_h + (rows - 1) * gutter
        page = Image.new("RGB", (page_w, page_h), "white")
        draw = ImageDraw.Draw(page)
        for index, image in enumerate(images):
            row, col = divmod(index, columns)
            cell_x = margin + col * (cell_w + gutter)
            cell_y = margin + row * (cell_h + gutter)
            fitted = image.copy()
            fitted.thumbnail((cell_w - border * 2, cell_h - border * 2), Image.Resampling.LANCZOS)
            paste_x = cell_x + (cell_w - fitted.width) // 2
            paste_y = cell_y + (cell_h - fitted.height) // 2
            page.paste(fitted, (paste_x, paste_y))
            if border > 0:
                draw.rectangle(
                    [cell_x, cell_y, cell_x + cell_w - 1, cell_y + cell_h - 1],
                    outline="black",
                    width=border,
                )
        return (_pil_to_tensor(page),)


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    width = max(8, int(width))
    height = max(8, int(height))
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale)))),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _fit_width(image: Image.Image, width: int) -> Image.Image:
    width = max(8, int(width))
    height = max(8, int(round(image.height * (width / image.width))))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _page_wide_top(images, columns, gutter, margin, border) -> Image.Image:
    top_image, *rest = images
    columns = max(1, min(int(columns), len(rest)))
    cell_w = max(image.width for image in rest)
    cell_h = max(image.height for image in rest)
    content_w = columns * cell_w + (columns - 1) * gutter
    inner = max(0, int(border))
    top_fitted = _fit_width(top_image, max(8, content_w - inner * 2))
    top_h = top_fitted.height + inner * 2
    rows = (len(rest) + columns - 1) // columns
    page_w = margin * 2 + content_w
    page_h = margin * 2 + top_h + gutter + rows * cell_h + (rows - 1) * gutter
    page = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(page)
    page.paste(top_fitted, (margin + inner, margin + inner))
    if border > 0:
        draw.rectangle([margin, margin, margin + content_w - 1, margin + top_h - 1], outline="black", width=border)
    for index, image in enumerate(rest):
        row, col = divmod(index, columns)
        cell_x = margin + col * (cell_w + gutter)
        cell_y = margin + top_h + gutter + row * (cell_h + gutter)
        fitted = image.copy()
        fitted.thumbnail((cell_w - inner * 2, cell_h - inner * 2), Image.Resampling.LANCZOS)
        paste_x = cell_x + (cell_w - fitted.width) // 2
        paste_y = cell_y + (cell_h - fitted.height) // 2
        page.paste(fitted, (paste_x, paste_y))
        if border > 0:
            draw.rectangle(
                [cell_x, cell_y, cell_x + cell_w - 1, cell_y + cell_h - 1],
                outline="black",
                width=border,
            )
    return page


class ComixesPublishReference:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "filename": ("STRING", {"default": "canonical.png"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "publish"
    CATEGORY = "comixes"

    def publish(self, image, filename):
        name = Path(str(filename)).name
        if not name.lower().endswith(".png") or not re.fullmatch(r"[A-Za-z0-9_\-]+\.png", name):
            raise RuntimeError("Имя эталона: буквы, цифры и подчёркивание, расширение .png.")
        path = COMFY_INPUT / name
        _tensor_to_pil(image).save(path)
        print(f"[comixes] Эталон записан в {path}")
        return (image,)


class ComixesSaveDataset:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "character": ("STRING", {"default": "vera.json"}),
                "filename": ("STRING", {"default": "01_front_full"}),
                "scene": ("STRING", {"multiline": True, "default": "front view, full body, simple grey background"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "path")
    FUNCTION = "save"
    CATEGORY = "comixes"

    def save(self, image, character, filename, scene):
        card = load_card(character)
        stem = Path(str(filename)).stem
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", stem):
            raise RuntimeError("Имя кадра датасета: буквы, цифры, _ и -.")
        caption = dataset_caption(card, scene)
        folder = DATASETS / card["name"].lower() / "images"
        folder.mkdir(parents=True, exist_ok=True)
        image_path = folder / f"{stem}.png"
        text_path = folder / f"{stem}.txt"
        _tensor_to_pil(image).save(image_path)
        text_path.write_text(caption + "\n", encoding="utf-8")
        print(f"[comixes] Датасет: {image_path}")
        return (image, str(image_path))


class ComixesReferenceLock:
    """IP-Adapter по эталону. Серый плейсхолдер пропускается, чтобы не красить кадр в пустоту."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "image": ("IMAGE",),
                "weight": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.5, "step": 0.01}),
                "start_at": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "end_at": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "apply"
    CATEGORY = "comixes"

    def apply(self, model, image, weight, start_at, end_at):
        sample = image.detach().float()[0].reshape(-1, image.shape[-1])
        picked = sample[:: max(1, sample.shape[0] // 4000)]
        quantized = (picked * 16).round().to(torch.int32)
        colors = {tuple(int(channel) for channel in row) for row in quantized.tolist()}
        if weight <= 0 or len(colors) < 12:
            print("[comixes] Эталон пустой или это серая заглушка, IP-Adapter пропущен.")
            return (model,)
        import nodes

        loader = nodes.NODE_CLASS_MAPPINGS["IPAdapterUnifiedLoader"]()
        locked, adapter = loader.load_models(model, "PLUS (high strength)")
        applied = nodes.NODE_CLASS_MAPPINGS["IPAdapter"]().apply_ipadapter(
            locked,
            adapter,
            image,
            float(weight),
            float(start_at),
            float(end_at),
            "prompt is more important",
        )
        return applied


class ComixesSfx:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "text": ("STRING", {"default": ""}),
                "x": ("FLOAT", {"default": 0.72, "min": 0.0, "max": 1.0, "step": 0.01}),
                "y": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 1.0, "step": 0.01}),
                "scale": ("FLOAT", {"default": 0.16, "min": 0.04, "max": 0.5, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "draw"
    CATEGORY = "comixes"

    def draw(self, image, text, x, y, scale):
        from comixes_lib.lettering import draw_sfx

        frames = []
        for index in range(image.shape[0]):
            pil = _tensor_to_pil(image[index:index + 1])
            frames.append(_pil_to_tensor(draw_sfx(pil, text, x, y, scale)))
        return (torch.cat(frames, dim=0),)


class ComixesTrainLora:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "character": ("STRING", {"default": "vera.json"}),
                "model_family": (list(CHECKPOINT_NAMES),),
                "steps": ("INT", {"default": 1600, "min": 100, "max": 8000, "step": 50}),
                "rank": ("INT", {"default": 16, "min": 4, "max": 64, "step": 4}),
                "alpha": ("FLOAT", {"default": 16.0, "min": 1.0, "max": 64.0, "step": 1.0}),
                "lr": ("FLOAT", {"default": 0.0001, "min": 0.00001, "max": 0.001, "step": 0.00001}),
                "resolution": ("INT", {"default": 1024, "min": 512, "max": 1024, "step": 64}),
                "save_every": ("INT", {"default": 400, "min": 50, "max": 2000, "step": 50}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("status", "lora_path")
    FUNCTION = "train"
    CATEGORY = "comixes"

    def train(self, character, model_family, steps, rank, alpha, lr, resolution, save_every):
        import subprocess

        import comfy.model_management as model_management

        card = load_card(character)
        folder = DATASETS / card["name"].lower() / "images"
        pictures = [
            path for path in folder.glob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg"} and path.with_suffix(".txt").is_file()
        ]
        if len(pictures) < 8:
            raise RuntimeError(
                f"В {folder} нужно минимум 8 кадров с подписью .txt. Сейчас {len(pictures)}. "
                "Сначала 07, потом несколько вариантов в 08. Кривые глаза в обучение не клади."
            )
        model_management.unload_all_models()
        model_management.soft_empty_cache()
        command = [
            str(PYTHON),
            "-s",
            str(PROJECT / "tools" / "train_lora.py"),
            "--character",
            Path(character).name,
            "--family",
            model_family,
            "--steps",
            str(int(steps)),
            "--rank",
            str(int(rank)),
            "--alpha",
            str(float(alpha)),
            "--lr",
            str(float(lr)),
            "--resolution",
            str(int(resolution)),
            "--save-every",
            str(int(save_every)),
        ]
        log_path = folder.parent / "train.log"
        print(f"[comixes] Обучение {card['name']} на {model_family}. Лог: {log_path}")
        tail: list[str] = []
        with log_path.open("w", encoding="utf-8") as handle:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="")
                handle.write(line)
                tail.append(line)
                if len(tail) > 60:
                    tail = tail[-60:]
            code = process.wait()
        lora_path = str(card.get("lora") or "")
        if code != 0:
            detail = "".join(tail)[-1800:]
            raise RuntimeError(
                "Обучение остановилось. Если в логе CUDA out of memory, закрой ComfyUI и запусти "
                f"train_lora.bat --character {Path(character).name} --family {model_family}\n{detail}"
            )
        status = _status_image(f"LoRA готова\n{card.get('lora', '')}\nкадров: {len(pictures)}")
        return (status, lora_path)


def _status_image(text: str) -> torch.Tensor:
    image = Image.new("RGB", (768, 384), "white")
    draw = ImageDraw.Draw(image)
    face = _font(36)
    draw.multiline_text((36, 48), text, fill="black", font=face, spacing=12)
    return _pil_to_tensor(image)


NODE_CLASS_MAPPINGS = {
    "ComixesLoadFamily": ComixesLoadFamily,
    "ComixesCharacterPrompt": ComixesCharacterPrompt,
    "ComixesGuardText": ComixesGuardText,
    "ComixesOptionalLora": ComixesOptionalLora,
    "ComixesSpeechBubble": ComixesSpeechBubble,
    "ComixesFitLongSide": ComixesFitLongSide,
    "ComixesFitCanvas": ComixesFitCanvas,
    "ComixesPage": ComixesPage,
    "ComixesPublishReference": ComixesPublishReference,
    "ComixesSaveDataset": ComixesSaveDataset,
    "ComixesReferenceLock": ComixesReferenceLock,
    "ComixesSfx": ComixesSfx,
    "ComixesTrainLora": ComixesTrainLora,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ComixesLoadFamily": "Comixes: модель",
    "ComixesCharacterPrompt": "Comixes: персонаж",
    "ComixesGuardText": "Comixes: проверка текста",
    "ComixesOptionalLora": "Comixes: LoRA персонажа",
    "ComixesSpeechBubble": "Comixes: облачка",
    "ComixesFitLongSide": "Comixes: вписать в VRAM",
    "ComixesFitCanvas": "Comixes: вписать без деформации",
    "ComixesPage": "Comixes: страница",
    "ComixesPublishReference": "Comixes: записать эталон",
    "ComixesSaveDataset": "Comixes: кадр в датасет",
    "ComixesReferenceLock": "Comixes: замок внешности",
    "ComixesSfx": "Comixes: звук",
    "ComixesTrainLora": "Comixes: обучить LoRA",
}
