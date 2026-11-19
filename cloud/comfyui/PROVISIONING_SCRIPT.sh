#!/usr/bin/env bash
set -Eeuo pipefail

# Comixes cloud ComfyUI bundle:
#   - WAI Illustrious v17: one-pass character/style LoCon + optional reference/pose conditioning
#   - Official MiniMax-H3-Image: high-fidelity reference editing without Qwen Image
#   - MiniMax H3 Eros ImageEdit: interaction-specialized 5090 HQ / RTX 6000 Pro profiles
#
# Required acknowledgements are intentionally explicit because these model
# families have different licenses. See README_RU.md before setting them to 1.

WORKSPACE="${WORKSPACE:-/workspace}"
COMFYUI_DIR="${COMFYUI_DIR:-${WORKSPACE}/ComfyUI}"
if [[ -f /venv/main/bin/activate || -f /venv/main/Scripts/activate ]]; then
  DEFAULT_VENV_DIR="/venv/main"
else
  DEFAULT_VENV_DIR="${WORKSPACE}/.venv"
fi
VENV_DIR="${VENV_DIR:-${DEFAULT_VENV_DIR}}"
PORT="${PORT:-8188}"
COMFYUI_REF="${COMFYUI_REF:-v0.46.0}"
INSTALL_WAI="${INSTALL_WAI:-1}"
INSTALL_H3="${INSTALL_H3:-1}"
INSTALL_H3_IMAGE="${INSTALL_H3_IMAGE:-1}"
GPU_PROFILE="${GPU_PROFILE:-auto}"
EFFECTIVE_GPU_PROFILE=""
VERIFY_SHA256="${VERIFY_SHA256:-1}"
ACCEPT_WAI_LICENSE="${ACCEPT_WAI_LICENSE:-0}"
ACCEPT_MINIMAX_H3_LICENSE="${ACCEPT_MINIMAX_H3_LICENSE:-0}"
ACCEPT_MINIMAX_H3_IMAGE_LICENSE="${ACCEPT_MINIMAX_H3_IMAGE_LICENSE:-0}"
PROVISION_ONLY="${PROVISION_ONLY:-0}"
FORCE_PROVISION="${FORCE_PROVISION:-0}"
HF_TOKEN="${HF_TOKEN:-}"
CIVITAI_TOKEN="${CIVITAI_TOKEN:-}"
INSTALL_SYSTEM_PACKAGES="${INSTALL_SYSTEM_PACKAGES:-1}"
DISK_RESERVE_GIB="${DISK_RESERVE_GIB:-20}"
COMIXES_REPO_URL="${COMIXES_REPO_URL:-}"
COMIXES_REF="${COMIXES_REF:-main}"
INITIAL_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${INITIAL_SCRIPT_DIR}/workflows/wai_v17_lora_hq_onepass.json" \
      && -f "${INITIAL_SCRIPT_DIR}/../../comfy_nodes/comixes_comic/__init__.py" ]]; then
  DEFAULT_COMIXES_PROJECT="$(cd -- "${INITIAL_SCRIPT_DIR}/../.." && pwd)"
else
  DEFAULT_COMIXES_PROJECT="${WORKSPACE}/comixes-workflow"
fi
COMIXES_PROJECT="${COMIXES_PROJECT:-${DEFAULT_COMIXES_PROJECT}}"
SCRIPT_DIR="${INITIAL_SCRIPT_DIR}"

COMFYUI_REPO="https://github.com/comfyanonymous/ComfyUI.git"
MIN_COMFY_VERSION="0.46.0"
MIN_PLAGUEKIND_VERSION="1.6.2"

declare -a H3_NODES=(
  "https://github.com/PlagueKind/Comfyui-PlagueKind-Nodes.git|cc944b5064d1b15fc77664c7138d9752bba66302"
  "https://github.com/kijai/ComfyUI-KJNodes.git|aa2b5ea5e7f61b51f5d26d726f23c1d74e951016"
  "https://github.com/rgthree/rgthree-comfy.git|bc48c6aaeca87bedbc14245d89f9bc6be37a630e"
  "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git|4d907bee61e92c2e65af3bd6383a4e4d356126d1"
  "https://github.com/Luisacaotica/ComfyUI-MiniMaxH3Mod.git|54f93eb6569fe35c9303e9bceb1c8b66c5722bbf"
  "https://github.com/silveroxides/ComfyUI_PowerShiftScheduler.git|770d7b8e4104b8d864d1fed0a65713e4a3e7a953"
)

declare -a WAI_NODES=(
  "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git|a0f451a5113cf9becb0847b92884cb10cbdec0ef"
  "https://github.com/Fannovel16/comfyui_controlnet_aux.git|c2655d2970d810d8a3d71deed204cdf416b66132"
)

declare -a ASSETS=()

log() { printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

is_enabled() {
  [[ "${1}" == "1" || "${1,,}" == "true" || "${1,,}" == "yes" ]]
}

run_privileged() {
  if [[ "$(id -u)" == "0" ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo -n "$@"
  else
    die "System packages are missing and root/passwordless sudo is unavailable. Use an Ubuntu GPU image with Python 3, git, curl, ffmpeg and build tools, or grant provisioning sudo."
  fi
}

bootstrap_host() {
  if is_enabled "${INSTALL_SYSTEM_PACKAGES}" && command -v apt-get >/dev/null 2>&1; then
    local -a packages=(
      ca-certificates coreutils curl git python3 python3-pip python3-venv
      build-essential cmake ninja-build pkg-config unzip ffmpeg
      libgl1 libglib2.0-0 libgomp1 libsm6 libxext6 libxrender1
    )
    local -a missing=()
    local package
    for package in "${packages[@]}"; do
      dpkg-query -W -f='${Status}' "${package}" 2>/dev/null | grep -q 'install ok installed' || missing+=("${package}")
    done
    if (( ${#missing[@]} )); then
      log "Installing host packages: ${missing[*]}"
      run_privileged apt-get update
      run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
    fi
  fi

  local -a missing_commands=()
  local command_name
  for command_name in git curl python3 sha256sum ffmpeg; do
    command -v "${command_name}" >/dev/null 2>&1 || missing_commands+=("${command_name}")
  done
  (( ${#missing_commands[@]} == 0 )) || \
    die "Missing host commands: ${missing_commands[*]}. Use Ubuntu/Debian or install them before provisioning."
}

resolve_gpu_profile() {
  case "${GPU_PROFILE,,}" in
    rtx5090|5090) EFFECTIVE_GPU_PROFILE="rtx5090" ;;
    rtx6000|rtx6000pro|6000|6000pro) EFFECTIVE_GPU_PROFILE="rtx6000" ;;
    auto)
      if is_enabled "${PROVISIONING_SELF_TEST:-0}" && ! command -v nvidia-smi >/dev/null 2>&1; then
        EFFECTIVE_GPU_PROFILE="rtx5090"
      else
        command -v nvidia-smi >/dev/null 2>&1 || die "GPU_PROFILE=auto requires nvidia-smi; set GPU_PROFILE=rtx5090 or rtx6000 explicitly."
        local vram_mib
        vram_mib="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1 | tr -d ' ')"
        [[ "${vram_mib}" =~ ^[0-9]+$ ]] || die "Cannot read GPU VRAM from nvidia-smi."
        if (( vram_mib >= 81920 )); then
          EFFECTIVE_GPU_PROFILE="rtx6000"
        elif (( vram_mib >= 30000 )); then
          EFFECTIVE_GPU_PROFILE="rtx5090"
        else
          die "Production bundle requires at least 30 GiB VRAM; detected ${vram_mib} MiB."
        fi
      fi
        ;;
    *) die "GPU_PROFILE must be auto, rtx5090 or rtx6000." ;;
  esac
  log "Selected production GPU profile: ${EFFECTIVE_GPU_PROFILE}"
}

verify_gpu_runtime() {
  command -v nvidia-smi >/dev/null 2>&1 || \
    die "nvidia-smi is unavailable. The cloud image must expose an NVIDIA driver/GPU runtime before provisioning."
  local vram_mib
  vram_mib="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1 | tr -d ' ')"
  [[ "${vram_mib}" =~ ^[0-9]+$ ]] || die "Cannot read GPU VRAM from nvidia-smi."
  if [[ "${EFFECTIVE_GPU_PROFILE}" == "rtx6000" ]] && (( vram_mib < 81920 )); then
    die "GPU_PROFILE=rtx6000 requires at least 80 GiB VRAM for the full BF16 profile; detected ${vram_mib} MiB."
  fi
  if [[ "${EFFECTIVE_GPU_PROFILE}" == "rtx5090" ]] && (( vram_mib < 30000 )); then
    die "GPU_PROFILE=rtx5090 requires at least 30 GiB VRAM; detected ${vram_mib} MiB."
  fi
  log "NVIDIA runtime available; detected ${vram_mib} MiB VRAM"
}

add_asset() {
  local label="$1" url="$2" relative_path="$3" expected_bytes="$4" sha256="$5"
  ASSETS+=("${label}|${url}|${relative_path}|${expected_bytes}|${sha256}")
}

check_license_acknowledgements() {
  if is_enabled "${INSTALL_WAI}" && ! is_enabled "${ACCEPT_WAI_LICENSE}"; then
    die "WAI Illustrious v17 has its own model terms. Read README_RU.md and rerun with ACCEPT_WAI_LICENSE=1."
  fi
  if is_enabled "${INSTALL_H3}" && ! is_enabled "${ACCEPT_MINIMAX_H3_LICENSE}"; then
    die "H3 uses the MiniMax H3 Community License with territorial restrictions. Read README_RU.md and rerun with ACCEPT_MINIMAX_H3_LICENSE=1."
  fi
  if is_enabled "${INSTALL_H3_IMAGE}" && ! is_enabled "${ACCEPT_MINIMAX_H3_IMAGE_LICENSE}"; then
    die "MiniMax-H3-Image has its own Community License. Read README_RU.md and rerun with ACCEPT_MINIMAX_H3_IMAGE_LICENSE=1."
  fi
}

activate_python() {
  if [[ ! -f "${VENV_DIR}/bin/activate" && ! -f "${VENV_DIR}/Scripts/activate" ]]; then
    log "Creating Python virtual environment in ${VENV_DIR}"
    mkdir -p "$(dirname -- "${VENV_DIR}")" || \
      die "Cannot create the parent directory for ${VENV_DIR}; choose a writable VENV_DIR."
    python3 -m venv "${VENV_DIR}" || \
      die "Cannot create ${VENV_DIR}. Set VENV_DIR to a writable directory such as ${WORKSPACE}/venv."
  fi

  if [[ -f "${VENV_DIR}/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
  else
    # shellcheck disable=SC1091
    source "${VENV_DIR}/Scripts/activate"
  fi

  command -v python >/dev/null 2>&1 || die "python is not available"
  command -v pip >/dev/null 2>&1 || die "pip is not available"
  command -v git >/dev/null 2>&1 || die "git is not available"
  command -v curl >/dev/null 2>&1 || die "curl is not available"
  if is_enabled "${VERIFY_SHA256}"; then
    command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required while VERIFY_SHA256=1"
  fi
  export COMIXES_PROJECT
  export COMIXES_COMFY_ROOT="$(dirname -- "${COMFYUI_DIR}")"
  export COMIXES_PYTHON="$(command -v python)"
}

prepare_python_tooling() {
  python -m pip install --disable-pip-version-check --no-cache-dir --upgrade pip setuptools wheel
}

checkout_repo_at_ref() {
  local repo="$1" destination="$2" ref="$3"

  if [[ ! -e "${destination}" ]]; then
    log "Cloning ${repo}"
    git clone --recursive "${repo}" "${destination}"
  elif [[ ! -d "${destination}/.git" ]]; then
    die "${destination} exists but is not a git checkout"
  fi

  if ! git -C "${destination}" diff --quiet || ! git -C "${destination}" diff --cached --quiet; then
    die "${destination} has local changes. Commit/stash them before provisioning; no destructive reset was attempted."
  fi

  log "Pinning ${destination} to ${ref}"
  git -C "${destination}" fetch --tags origin
  git -C "${destination}" cat-file -e "${ref}^{commit}" 2>/dev/null || \
    git -C "${destination}" fetch origin "${ref}"
  local commit
  commit="$(git -C "${destination}" rev-parse "${ref}^{commit}")"
  git -C "${destination}" checkout --detach "${commit}"
  git -C "${destination}" submodule update --init --recursive
}

ensure_comixes_bundle() {
  local workflows="${COMIXES_PROJECT}/cloud/comfyui/workflows"
  local nodes="${COMIXES_PROJECT}/comfy_nodes/comixes_comic/__init__.py"
  if [[ ! -f "${workflows}/wai_v17_lora_hq_onepass.json" || ! -f "${nodes}" ]]; then
    [[ -n "${COMIXES_REPO_URL}" ]] || die \
      "Comixes bundle is not present at ${COMIXES_PROJECT}. When running a lone raw provisioning script, set COMIXES_REPO_URL to the Git repository containing cloud/comfyui and comfy_nodes (optionally pin COMIXES_REF)."
    mkdir -p "$(dirname -- "${COMIXES_PROJECT}")"
    checkout_repo_at_ref "${COMIXES_REPO_URL}" "${COMIXES_PROJECT}" "${COMIXES_REF}"
  fi
  [[ -f "${workflows}/wai_v17_lora_hq_onepass.json" && -f "${nodes}" ]] || \
    die "The Comixes repository does not contain the required cloud workflows and custom nodes."
  COMIXES_PROJECT="$(cd -- "${COMIXES_PROJECT}" && pwd)"
  SCRIPT_DIR="${COMIXES_PROJECT}/cloud/comfyui"
  export COMIXES_PROJECT
  log "Using Comixes bundle from ${COMIXES_PROJECT}"
}

install_comfyui() {
  mkdir -p "${WORKSPACE}"
  checkout_repo_at_ref "${COMFYUI_REPO}" "${COMFYUI_DIR}" "${COMFYUI_REF}"

  if [[ -f "${COMFYUI_DIR}/requirements.txt" ]]; then
    log "Installing ComfyUI requirements"
    pip install --disable-pip-version-check --no-cache-dir -r "${COMFYUI_DIR}/requirements.txt"
  fi
}

require_comfy_version() {
  python - "${COMFYUI_DIR}" "${MIN_COMFY_VERSION}" <<'PY'
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
minimum = tuple(map(int, sys.argv[2].split(".")))
version_file = root / "comfyui_version.py"
if not version_file.exists():
    raise SystemExit("ComfyUI version file is missing; update ComfyUI")
match = re.search(r'__version__\s*=\s*["\']([^"\']+)', version_file.read_text(encoding="utf-8"))
if not match:
    raise SystemExit("Cannot parse ComfyUI version")
current = tuple(map(int, match.group(1).split(".")[:3]))
if current < minimum:
    raise SystemExit(f"ComfyUI {match.group(1)} is too old; need >= {sys.argv[2]}")
print(f"ComfyUI {match.group(1)} OK")
PY
}

ensure_h3_torch() {
  if python - <<'PY'
import re
import torch

version = tuple(map(int, re.match(r"(\d+)\.(\d+)", torch.__version__).groups()))
cuda = torch.version.cuda or ""
assert version >= (2, 13), (torch.__version__, cuda)
assert cuda.startswith("13.0"), (torch.__version__, cuda)
print(f"PyTorch {torch.__version__}, CUDA runtime {cuda}: OK")
PY
  then
    return
  fi

  log "Installing PyTorch >=2.13 for CUDA 13.0 required by H3 ImageEdit"
  pip install --disable-pip-version-check --no-cache-dir --upgrade \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130

  python - <<'PY'
import re
import torch

version = tuple(map(int, re.match(r"(\d+)\.(\d+)", torch.__version__).groups()))
cuda = torch.version.cuda or ""
assert version >= (2, 13), (torch.__version__, cuda)
assert cuda.startswith("13.0"), (torch.__version__, cuda)
print(f"PyTorch {torch.__version__}, CUDA runtime {cuda}: verified after install")
PY
}

install_h3_nodes() {
  local custom_nodes="${COMFYUI_DIR}/custom_nodes"
  mkdir -p "${custom_nodes}"

  local record repo ref
  for record in "${H3_NODES[@]}"; do
    IFS='|' read -r repo ref <<<"${record}"
    local name="${repo##*/}"
    name="${name%.git}"
    local destination="${custom_nodes}/${name}"
    checkout_repo_at_ref "${repo}" "${destination}" "${ref}"
    if [[ -f "${destination}/requirements.txt" ]]; then
      log "Installing requirements for ${name}"
      pip install --disable-pip-version-check --no-cache-dir -r "${destination}/requirements.txt"
    fi
  done

  python - "${custom_nodes}/Comfyui-PlagueKind-Nodes/pyproject.toml" "${MIN_PLAGUEKIND_VERSION}" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
minimum = tuple(map(int, sys.argv[2].split(".")))
if not path.exists():
    raise SystemExit(f"Missing {path}")
match = re.search(r'^version\s*=\s*["\']([^"\']+)', path.read_text(encoding="utf-8"), re.M)
if not match:
    raise SystemExit(f"Cannot parse version from {path}")
current = tuple(map(int, match.group(1).split(".")[:3]))
if current < minimum:
    raise SystemExit(f"PlagueKind nodes {match.group(1)} are too old; need >= {sys.argv[2]}")
print(f"PlagueKind nodes {match.group(1)} OK")
PY
}

install_wai_nodes() {
  local custom_nodes="${COMFYUI_DIR}/custom_nodes"
  mkdir -p "${custom_nodes}"

  local record repo ref
  for record in "${WAI_NODES[@]}"; do
    IFS='|' read -r repo ref <<<"${record}"
    local name="${repo##*/}"
    name="${name%.git}"
    local destination="${custom_nodes}/${name}"
    checkout_repo_at_ref "${repo}" "${destination}" "${ref}"
    if [[ -f "${destination}/requirements.txt" ]]; then
      log "Installing requirements for ${name}"
      pip install --disable-pip-version-check --no-cache-dir -r "${destination}/requirements.txt"
    fi
  done

  local comixes_source="${COMIXES_PROJECT}/comfy_nodes/comixes_comic"
  local comixes_target="${custom_nodes}/comixes_comic"
  [[ -f "${comixes_source}/__init__.py" ]] || die "Missing Comixes custom nodes: ${comixes_source}"
  if [[ -e "${comixes_target}" && ! -L "${comixes_target}" ]]; then
    die "${comixes_target} exists and is not the managed symlink"
  fi
  ln -sfn "${comixes_source}" "${comixes_target}"

  log "Installing WAI LoCon training dependencies"
  pip install --disable-pip-version-check --no-cache-dir --upgrade \
    diffusers transformers accelerate peft safetensors bitsandbytes
}

install_placeholder_inputs() {
  mkdir -p "${COMFYUI_DIR}/input"
  python - "${COMFYUI_DIR}/input/canonical.png" "${COMFYUI_DIR}/input/pose_placeholder.png" <<'PY'
from pathlib import Path
from PIL import Image, ImageDraw
import sys

for destination, label in zip(sys.argv[1:], ("replace with character/style reference", "replace with pose reference")):
    path = Path(destination)
    if path.exists():
        continue
    image = Image.new("RGB", (768, 1024), (210, 210, 210))
    draw = ImageDraw.Draw(image)
    draw.text((48, 480), label, fill=(30, 30, 30))
    image.save(path)
PY
}

register_assets() {
  ASSETS=()
  if is_enabled "${INSTALL_WAI}"; then
    add_asset "WAI Illustrious SDXL v17" \
      "https://huggingface.co/feiaitou/waiIllustriousSDXL_v170/resolve/fc1ba161dd47adba082472c027302b5f403e8893/waiIllustriousSDXL_v170.safetensors" \
      "models/checkpoints/waiIllustriousSDXL_v170.safetensors" 6938040682 \
      "f116b0c78ff441467b0cdc8f1936e1ed18ea31e9997c7b132b1b8db533f0bd04"
    add_asset "CLIP Vision ViT-H for SDXL IPAdapter" \
      "https://huggingface.co/h94/IP-Adapter/resolve/018e402774aeeddd60609b4ecdb7e298259dc729/models/image_encoder/model.safetensors" \
      "models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors" 2528373448 \
      "6ca9667da1ca9e0b0f75e46bb030f7e011f44f86cbfb8d5a36590fcd7507b030"
    add_asset "IPAdapter Plus SDXL ViT-H" \
      "https://huggingface.co/h94/IP-Adapter/resolve/018e402774aeeddd60609b4ecdb7e298259dc729/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors" \
      "models/ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors" 847517512 \
      "3f5062b8400c94b7159665b21ba5c62acdcd7682262743d7f2aefedef00e6581"
    add_asset "Xinsir Union SDXL ProMax ControlNet" \
      "https://huggingface.co/xinsir/controlnet-union-sdxl-1.0/resolve/801a4a3fa3d4c936f4feea95b98607bc6726f80c/diffusion_pytorch_model_promax.safetensors" \
      "models/controlnet/xinsir-union-sdxl-promax.safetensors" 2513342408 \
      "9fae2e50cb431bfcbe05822b59ec2228df545ef27f711dea8949e9f4ed9f7cdc"
    add_asset "4x UltraSharp upscaler" \
      "https://huggingface.co/uwg/upscaler/resolve/f6bace545e358eab5491f8f39b90a2dd42e8cc77/ESRGAN/4x-UltraSharp.pth" \
      "models/upscale_models/4x-UltraSharp.pth" 66961958 \
      "a5812231fc936b42af08a5edba784195495d303d5b3248c24489ef0c4021fe01"
  fi

  if is_enabled "${INSTALL_H3}"; then
    add_asset "H3 audio VAE for RefMod creation" \
      "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4b53a35191437de05370da548e59aeabe2a5a09a/vae/minimax_h3_audio_vae_fp32.safetensors" \
      "models/vae/minimax_h3_audio_vae_fp32.safetensors" 605254808 \
      "8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48"
    add_asset "H3 LynnReal encoder VAE" \
      "https://huggingface.co/Kijai/MiniMax-H3-experimental/resolve/c2e7b89b1800123c49a0f620a1932c01d8952256/minimax_h3_lynnreal_light_vae_int8_convrot.safetensors" \
      "models/vae/minimax_h3_lynnreal_light_vae_int8_convrot.safetensors" 2137493384 \
      "f11f8b9b96c9dd22b36bc6c18464b6929c207d247e6d865d90fe31588e58e7e2"
    add_asset "H3 preview VAE" \
      "https://huggingface.co/Kijai/MiniMax-H3-TAE/resolve/bcec7bc2b0e0a277bd0d5c028605590de711bfb6/vae_approx/taeh3.safetensors" \
      "models/vae_approx/taeh3.safetensors" 9791388 \
      "f0f60fa072089997f817402098c2fd90777cb2660dd79cf5df42fc1e3e08e527"
    add_asset "P-H3 Image edit LoRA" \
      "https://huggingface.co/PrunaAI/P-H3-Image-Comfy/resolve/1bf3b0cee1bc1ff45408d0af7a246ae594fbdf74/loras/p-h3-image_lora_bf16.safetensors" \
      "models/loras/H3/p-h3-image_lora_bf16.safetensors" 1956195360 \
      "0e9013ae2873e3415dcb7bb59a9677293bdbdb6f663e138a79bb9bdced00ea61"

    if [[ "${EFFECTIVE_GPU_PROFILE}" == "rtx6000" ]]; then
      add_asset "10Eros Max beta7 fix1 full precision" \
        "https://huggingface.co/TenStrip/10Eros-Max/resolve/804e16fbc3c894764353f2914e5b0943da45f9f4/10Eros_Max_h3_8stepTURBO_beta7_fix1.safetensors" \
        "models/diffusion_models/video/10Eros_Max_h3_8stepTURBO_beta7_fix1.safetensors" 40265608072 \
        "8a670bf9962e7379946f10bede480d3e603d0d1ed2ab02c22d36398f4c796a29"
      add_asset "H3 Qwen3-VL 32B HQ protected encoder" \
        "https://huggingface.co/LokkenJP/TenEros_Max_optimized_learned/resolve/5bb5da8183916c380bad115cefd190ccfd139598/text_encoder/qwen3vl_32b_minimax_h3_native_w6g16_int8protected_23.03gb.safetensors" \
        "models/text_encoders/qwen3vl_32b_minimax_h3_native_w6g16_int8protected_23.03gb.safetensors" 23026371302 \
        "a7c6583e6d6df2b370381797c56a73dec26f5fc0ed659866c9e33495615ca159"
      add_asset "P-H3 Image BF16 decoder VAE" \
        "https://huggingface.co/PrunaAI/P-H3-Image-Comfy/resolve/1bf3b0cee1bc1ff45408d0af7a246ae594fbdf74/vae/p-h3-image_vae_bf16.safetensors" \
        "models/vae/p-h3-image_vae_bf16.safetensors" 5559036680 \
        "a1f2a7a98d0f2d1e761656fc5701dd43d7cf46d1bbdaa5d866a3e961e97487d7"
    else
      add_asset "10Eros Max beta7 fix1 activation-learned HQ" \
        "https://huggingface.co/LokkenJP/TenEros_Max_optimized_learned/resolve/5bb5da8183916c380bad115cefd190ccfd139598/10Eros_Max_h3_8stepTURBO_beta7_fix1_activation_learned_HQ.safetensors" \
        "models/diffusion_models/video/10Eros_Max_h3_8stepTURBO_beta7_fix1_activation_learned_HQ.safetensors" 18734317942 \
        "958717347e004fd2b9dc08966d8b7464e1b6004ceae263b5de730a4a1bcb999b"
      add_asset "H3 Qwen3-VL 32B protected 5090 encoder" \
        "https://huggingface.co/LokkenJP/TenEros_Max_optimized_learned/resolve/5bb5da8183916c380bad115cefd190ccfd139598/text_encoder/qwen3vl_32b_minimax_h3_native_w4g128_w6protected_15.35gb.safetensors" \
        "models/text_encoders/qwen3vl_32b_minimax_h3_native_w4g128_w6protected_15.35gb.safetensors" 15354664454 \
        "61cdec876d0a34ced0809664434c013ff2fc8c3f0a39beffae6162942c97c446"
      add_asset "P-H3 Image int8 decoder VAE" \
        "https://huggingface.co/PrunaAI/P-H3-Image-Comfy/resolve/1bf3b0cee1bc1ff45408d0af7a246ae594fbdf74/vae/p-h3-image_vae_int8_convrot.safetensors" \
        "models/vae/p-h3-image_vae_int8_convrot.safetensors" 3146996440 \
        "583e0d43354b6b833aa9a0815a5fac831b1ef6d0c19a7eaa0616980a3dab5ffe"
    fi
  fi

  if is_enabled "${INSTALL_H3_IMAGE}"; then
    add_asset "Official MiniMax-H3-Image FP16 VAE" \
      "https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/89c635085f539d03ad35485ed542c5a286e3c6d6/vae/minimax_h3_image_vae_fp16.safetensors" \
      "models/vae/minimax_h3_image_vae_fp16.safetensors" 1168505312 \
      "d80e9c2e5cfc9844869961ff5a58c9a9e52182df6bfb30b26018dd7f348721af"

    if [[ "${EFFECTIVE_GPU_PROFILE}" == "rtx6000" ]]; then
      add_asset "Official MiniMax-H3-Image pruned BF16 DiT" \
        "https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/89c635085f539d03ad35485ed542c5a286e3c6d6/diffusion_models/minimax_h3_image_pruned_bf16.safetensors" \
        "models/diffusion_models/minimax_h3_image_pruned_bf16.safetensors" 40234657162 \
        "a767f5325db019588b3491a93d80288d336c826a7aeb87bec67675e554367222"
      add_asset "Official MiniMax H3 BF16 text/reference encoder" \
        "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4b53a35191437de05370da548e59aeabe2a5a09a/text_encoders/qwen3vl_32b_minimax_h3_bf16.safetensors" \
        "models/text_encoders/qwen3vl_32b_minimax_h3_bf16.safetensors" 51506295256 \
        "600d567f6a9629c8574e8e7041b199bdd9c59a986afa7906910a81919610607d"
    else
      add_asset "Official MiniMax-H3-Image W4A8 DiT for RTX 5090" \
        "https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/89c635085f539d03ad35485ed542c5a286e3c6d6/diffusion_models/minimax_h3_image_pruned_w4a8.safetensors" \
        "models/diffusion_models/minimax_h3_image_pruned_w4a8.safetensors" 12549794530 \
        "517cc19b85348386f4df7c806dce80d839d0899e7cdaa3e1dbb09de964381dbb"
      add_asset "Official MiniMax H3 NVFP4-AWQ text/reference encoder for RTX 5090" \
        "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4b53a35191437de05370da548e59aeabe2a5a09a/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" \
        "models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" 15687142551 \
        "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6"
    fi
  fi
}

validate_existing_asset() {
  local target="$1" expected_bytes="$2" expected_sha256="$3"
  [[ -f "${target}" ]] || return 1
  local actual
  actual="$(stat -c '%s' "${target}")"
  [[ "${actual}" == "${expected_bytes}" ]] || \
    die "Existing file has the wrong size: ${target} (${actual}, expected ${expected_bytes}). Move it aside and rerun."

  if is_enabled "${VERIFY_SHA256}"; then
    local marker="${target}.sha256.ok"
    if [[ -f "${marker}" ]] && [[ "$(<"${marker}")" == "${expected_sha256}" ]] && [[ ! "${target}" -nt "${marker}" ]]; then
      return 0
    fi
    log "Verifying SHA-256: ${target}"
    local actual_sha256
    actual_sha256="$(sha256sum "${target}" | awk '{print $1}')"
    [[ "${actual_sha256}" == "${expected_sha256}" ]] || \
      die "SHA-256 mismatch: ${target} (${actual_sha256}, expected ${expected_sha256}). Move it aside and rerun."
    printf '%s' "${expected_sha256}" >"${marker}"
  fi
  return 0
}

preflight_disk_space() {
  local required=0 record label url relative expected sha256 target partial partial_size remaining
  for record in "${ASSETS[@]}"; do
    IFS='|' read -r label url relative expected sha256 <<<"${record}"
    target="${COMFYUI_DIR}/${relative}"
    if validate_existing_asset "${target}" "${expected}" "${sha256}"; then
      continue
    fi
    partial="${target}.part"
    partial_size=0
    [[ -f "${partial}" ]] && partial_size="$(stat -c '%s' "${partial}")"
    (( partial_size > expected )) && die "Partial file is larger than expected: ${partial}"
    remaining=$((expected - partial_size))
    required=$((required + remaining))
  done

  [[ "${DISK_RESERVE_GIB}" =~ ^[0-9]+$ ]] || die "DISK_RESERVE_GIB must be a non-negative integer."
  local available reserve=$((DISK_RESERVE_GIB * 1024 * 1024 * 1024))
  available="$(df -PB1 "${COMFYUI_DIR}" | awk 'NR==2 {print $4}')"
  printf 'Additional model bytes required: %s; free: %s; safety reserve: %s\n' \
    "${required}" "${available}" "${reserve}"
  (( available >= required + reserve )) || \
    die "Not enough disk space. Free at least $(((required + reserve - available + 1073741823) / 1073741824)) more GiB."
}

download_asset() {
  local label="$1" url="$2" relative="$3" expected_bytes="$4" expected_sha256="$5"
  local target="${COMFYUI_DIR}/${relative}"
  local partial="${target}.part"

  if validate_existing_asset "${target}" "${expected_bytes}" "${expected_sha256}"; then
    printf 'Already present: %s\n' "${target}"
    return
  fi

  mkdir -p "$(dirname -- "${target}")"
  local -a auth=()
  if [[ "${url}" == *huggingface.co* && -n "${HF_TOKEN}" ]]; then
    auth+=(--header="Authorization: Bearer ${HF_TOKEN}")
  elif [[ "${url}" == *civitai.com* && -n "${CIVITAI_TOKEN}" ]]; then
    auth+=(--header="Authorization: Bearer ${CIVITAI_TOKEN}")
  fi

  local actual=0
  [[ -f "${partial}" ]] && actual="$(stat -c '%s' "${partial}")"
  (( actual > expected_bytes )) && die "Partial file is larger than expected: ${partial}"
  if (( actual < expected_bytes )); then
    log "Downloading ${label} -> ${target}"
    curl --fail --location --retry 5 --retry-delay 3 --connect-timeout 30 \
      --continue-at - --output "${partial}" "${auth[@]}" "${url}"
  fi

  actual="$(stat -c '%s' "${partial}")"
  [[ "${actual}" == "${expected_bytes}" ]] || \
    die "Incomplete download for ${label}: ${actual} bytes, expected ${expected_bytes}. The .part file was kept for resume."

  if is_enabled "${VERIFY_SHA256}"; then
    log "Verifying downloaded SHA-256: ${label}"
    local actual_sha256
    actual_sha256="$(sha256sum "${partial}" | awk '{print $1}')"
    [[ "${actual_sha256}" == "${expected_sha256}" ]] || \
      die "SHA-256 mismatch for ${label}: ${actual_sha256}, expected ${expected_sha256}. The .part file was kept."
  fi

  mv -f "${partial}" "${target}"
  if is_enabled "${VERIFY_SHA256}"; then
    printf '%s' "${expected_sha256}" >"${target}.sha256.ok"
  fi
}

download_models() {
  local record label url relative expected sha256
  preflight_disk_space
  for record in "${ASSETS[@]}"; do
    IFS='|' read -r label url relative expected sha256 <<<"${record}"
    download_asset "${label}" "${url}" "${relative}" "${expected}" "${sha256}"
  done
  mkdir -p "${COMFYUI_DIR}/models/refmods"
}

install_workflows() {
  local destination="${COMFYUI_DIR}/user/default/workflows/comixes"
  if is_enabled "${VERIFY_SHA256}"; then
    [[ -f "${SCRIPT_DIR}/WORKFLOW_SHA256SUMS" ]] || die "Missing WORKFLOW_SHA256SUMS"
    (cd "${SCRIPT_DIR}/workflows" && sha256sum --check "${SCRIPT_DIR}/WORKFLOW_SHA256SUMS")
  fi
  mkdir -p "${destination}"
  local name enabled source target
  local -a managed_workflows=(
    "noctq_v4_bf16_t2i.json"
    "noctq_v4_bf16_reference_edit_hq.json"
    "wai_v17_lora_hq_onepass.json"
    "wai_v17_reference_hq_onepass.json"
    "wai_v17_train_character_style_locon.json"
    "h3_eros_5090_hq_image_edit_refmods.json"
    "h3_eros_6000_bf16_image_edit_refmods.json"
    "h3_image_5090_w4a8_hq_edit.json"
    "h3_image_6000_bf16_hq_edit.json"
  )

  for name in "${managed_workflows[@]}"; do
    enabled=0
    case "${name}" in
      noctq_v4_bf16_t2i.json|noctq_v4_bf16_reference_edit_hq.json)
        enabled=0
        ;;
      wai_v17_lora_hq_onepass.json|wai_v17_reference_hq_onepass.json|wai_v17_train_character_style_locon.json)
        is_enabled "${INSTALL_WAI}" && enabled=1
        ;;
      h3_eros_5090_hq_image_edit_refmods.json)
        is_enabled "${INSTALL_H3}" && [[ "${EFFECTIVE_GPU_PROFILE}" == "rtx5090" ]] && enabled=1
        ;;
      h3_eros_6000_bf16_image_edit_refmods.json)
        is_enabled "${INSTALL_H3}" && [[ "${EFFECTIVE_GPU_PROFILE}" == "rtx6000" ]] && enabled=1
        ;;
      h3_image_5090_w4a8_hq_edit.json)
        is_enabled "${INSTALL_H3_IMAGE}" && [[ "${EFFECTIVE_GPU_PROFILE}" == "rtx5090" ]] && enabled=1
        ;;
      h3_image_6000_bf16_hq_edit.json)
        is_enabled "${INSTALL_H3_IMAGE}" && [[ "${EFFECTIVE_GPU_PROFILE}" == "rtx6000" ]] && enabled=1
        ;;
    esac

    source="${SCRIPT_DIR}/workflows/${name}"
    target="${destination}/${name}"
    if [[ "${enabled}" == "1" ]]; then
      [[ -f "${source}" ]] || die "Missing bundled workflow: ${source}"
      install -m 0644 "${source}" "${target}"
    elif [[ -e "${target}" ]]; then
      rm -f -- "${target}"
      log "Removed disabled managed workflow ${name}"
    fi
  done
  log "Workflows installed in ${destination}"
}

managed_runtime_present() {
  [[ -f "${COMFYUI_DIR}/main.py" ]] || return 1
  [[ -f "${VENV_DIR}/bin/activate" || -f "${VENV_DIR}/Scripts/activate" ]] || return 1
  local record repo ref name
  if is_enabled "${INSTALL_WAI}"; then
    for record in "${WAI_NODES[@]}"; do
      IFS='|' read -r repo ref <<<"${record}"
      name="${repo##*/}"
      name="${name%.git}"
      [[ -d "${COMFYUI_DIR}/custom_nodes/${name}/.git" ]] || return 1
    done
    [[ -e "${COMFYUI_DIR}/custom_nodes/comixes_comic" ]] || return 1
  fi
  if is_enabled "${INSTALL_H3}" || is_enabled "${INSTALL_H3_IMAGE}"; then
    for record in "${H3_NODES[@]}"; do
      IFS='|' read -r repo ref <<<"${record}"
      name="${repo##*/}"
      name="${name%.git}"
      [[ -d "${COMFYUI_DIR}/custom_nodes/${name}/.git" ]] || return 1
    done
  fi
  return 0
}

provision() {
  check_license_acknowledgements
  resolve_gpu_profile
  verify_gpu_runtime
  bootstrap_host
  ensure_comixes_bundle
  activate_python
  prepare_python_tooling
  install_comfyui
  require_comfy_version

  if is_enabled "${INSTALL_WAI}"; then
    install_wai_nodes
  fi

  if is_enabled "${INSTALL_H3}" || is_enabled "${INSTALL_H3_IMAGE}"; then
    install_h3_nodes
  fi

  if is_enabled "${INSTALL_H3}" || is_enabled "${INSTALL_H3_IMAGE}"; then
    ensure_h3_torch
  fi

  install_placeholder_inputs
  register_assets
  download_models
  install_workflows
}

if is_enabled "${PROVISIONING_SELF_TEST:-0}"; then
  resolve_gpu_profile
  register_assets
  for record in "${ASSETS[@]}"; do
    IFS='|' read -r label url relative expected sha256 <<<"${record}"
    [[ -n "${label}" && -n "${url}" && -n "${relative}" ]] || die "Malformed asset record: ${record}"
    [[ "${expected}" =~ ^[0-9]+$ ]] || die "Invalid byte size in asset record: ${record}"
    [[ "${sha256}" =~ ^[0-9a-f]{64}$ ]] || die "Invalid SHA-256 in asset record: ${record}"
    [[ "${url}" != *"/resolve/main/"* ]] || die "Unpinned model URL: ${url}"
  done
  if is_enabled "${VERIFY_SHA256}"; then
    command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required while VERIFY_SHA256=1"
    [[ -f "${SCRIPT_DIR}/WORKFLOW_SHA256SUMS" ]] || die "Missing WORKFLOW_SHA256SUMS"
    (cd "${SCRIPT_DIR}/workflows" && sha256sum --check "${SCRIPT_DIR}/WORKFLOW_SHA256SUMS")
  fi
  if grep -REn '/(resolve|raw)/main/' "${SCRIPT_DIR}/workflows" --include='*.json'; then
    die "Bundled workflow contains unpinned Hugging Face model metadata"
  fi
  printf 'Provisioning manifest self-test: %s assets OK\n' "${#ASSETS[@]}"
  exit 0
fi

PROVISION_STAMP="${COMFYUI_DIR}/.comixes-provisioned"
PROVISION_SIGNATURE="v2|${COMFYUI_REF}|${GPU_PROFILE}|wai=${INSTALL_WAI}|h3=${INSTALL_H3}|h3image=${INSTALL_H3_IMAGE}|bundle=${COMIXES_REF}"
CURRENT_SIGNATURE=""
[[ -f "${PROVISION_STAMP}" ]] && CURRENT_SIGNATURE="$(<"${PROVISION_STAMP}")"

if is_enabled "${FORCE_PROVISION}" || [[ ! -f /.noprovisioning ]] \
    || [[ "${CURRENT_SIGNATURE}" != "${PROVISION_SIGNATURE}" ]] || ! managed_runtime_present; then
  provision
  mkdir -p "${COMFYUI_DIR}"
  printf '%s' "${PROVISION_SIGNATURE}" >"${PROVISION_STAMP}"
else
  log "/.noprovisioning and matching Comixes stamp found; reusing the verified installation"
  resolve_gpu_profile
  verify_gpu_runtime
  bootstrap_host
  ensure_comixes_bundle
  activate_python
  register_assets
  download_models
  install_workflows
fi

if is_enabled "${PROVISION_ONLY}"; then
  log "Provisioning completed; PROVISION_ONLY=1, ComfyUI was not started"
  exit 0
fi

log "Starting ComfyUI on 0.0.0.0:${PORT}"
cd "${COMFYUI_DIR}"
declare -a EXTRA_ARGS=()
if [[ -n "${COMFY_ARGS:-}" ]]; then
  # Simple whitespace-separated extra flags; do not place secrets here.
  read -r -a EXTRA_ARGS <<<"${COMFY_ARGS}"
fi
exec python main.py --listen 0.0.0.0 --port "${PORT}" "${EXTRA_ARGS[@]}"
