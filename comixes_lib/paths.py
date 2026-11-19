import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
COMFY_ROOT = Path(os.environ.get(
    "COMIXES_COMFY_ROOT", Path.home() / "Documents" / "MagoStudio" / "ComfyUI_windows_portable"
)).expanduser().resolve()
COMFY = COMFY_ROOT / "ComfyUI"
PYTHON = Path(os.environ.get("COMIXES_PYTHON", COMFY_ROOT / "python_embeded" / "python.exe"))
EDIT_RUNTIME = Path(os.environ.get("COMIXES_RUNTIME", "D:/ComixesStudio/runtime")).resolve()
EDIT_CORE = EDIT_RUNTIME / "ComfyUI-v0.45.0"
EDIT_DEPS = EDIT_RUNTIME / "deps-v0.45.0"
CHARACTERS = PROJECT / "characters"
DATASETS = PROJECT / "datasets"
WORKFLOWS = PROJECT / "workflows"
COMFY_INPUT = COMFY / "input"
COMFY_OUTPUT = COMFY / "output"
LORA_DIR = COMFY / "models" / "loras"
VAE = COMFY / "models" / "vae" / "sdxl_vae_fp16_fix.safetensors"
CHECKPOINT_NAMES = {
    "wai": "waiIllustriousSDXL_v170.safetensors",
}
CHECKPOINTS = {family: COMFY / "models" / "checkpoints" / name for family, name in CHECKPOINT_NAMES.items()}
