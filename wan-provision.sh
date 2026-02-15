#!/bin/bash
set -e
source /venv/main/bin/activate

WORKSPACE=${WORKSPACE:-/workspace}
COMFYUI_DIR="${WORKSPACE}/ComfyUI"

echo "=== ComfyUI: Brand Model I2I (SDXL + FaceID + ControlNet) ==="

APT_PACKAGES=()
PIP_PACKAGES=(
    "insightface"
    "onnxruntime-gpu"
)

NODES=(
    "https://github.com/cubiq/ComfyUI_IPAdapter_plus"
    "https://github.com/Fannovel16/comfyui_controlnet_aux"
    "https://github.com/ltdrdata/ComfyUI-Impact-Pack"
    "https://github.com/kijai/ComfyUI-KJNodes"
    "https://github.com/cubiq/ComfyUI_essentials"
    "https://github.com/rgthree/rgthree-comfy"
)

# ══════════════════════════════════════════════════════
# МОДЕЛИ — Juggernaut XL v9 (SDXL, NSFW-ready)
# ══════════════════════════════════════════════════════

CHECKPOINTS=(
    "https://huggingface.co/RunDiffusion/Juggernaut-XL-v9/resolve/main/Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
)

# ══════════════════════════════════════════════════════
# IP-ADAPTER FACEID — сохранение лица из референсов
# ══════════════════════════════════════════════════════

# FaceID Plus v2 SDXL — основная модель (1.5 GB)
IPADAPTER_MODELS=(
    "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl.bin"
)

# FaceID LoRA — ОБЯЗАТЕЛЬНО в models/loras/ (не в ipadapter!)
FACEID_LORAS=(
    "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl_lora.safetensors"
)

# ══════════════════════════════════════════════════════
# CONTROLNET — контроль позы через OpenPose
# ══════════════════════════════════════════════════════

# thibaud OpenPose SDXL v2 (~5 GB) — single-file safetensors
# https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0
CONTROLNET_MODELS=(
    "https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors"
)

# ══════════════════════════════════════════════════════
# CLIP VISION — энкодер для IP-Adapter
# ══════════════════════════════════════════════════════

# CLIP-ViT-H для FaceID Plus v2
# https://huggingface.co/h94/IP-Adapter
# Требует rename при скачивании (см. ниже)

### ─────────────────────────────────────────────
### DO NOT EDIT BELOW UNLESS YOU KNOW WHAT YOU ARE DOING
### ─────────────────────────────────────────────

function provisioning_start() {
    echo ""
    echo "##############################################"
    echo "#  OFM HUB — Brand Model I2I Workflow         #"
    echo "#  SDXL + FaceID + ControlNet OpenPose         #"
    echo "#  Полный контроль: лицо, поза, одежда, NSFW   #"
    echo "##############################################"
    echo ""

    provisioning_get_apt_packages
    provisioning_clone_comfyui
    provisioning_install_base_reqs
    provisioning_get_nodes
    provisioning_get_pip_packages

    # Стандартные загрузки (имя файла из URL)
    provisioning_get_files "${COMFYUI_DIR}/models/checkpoints"   "${CHECKPOINTS[@]}"
    provisioning_get_files "${COMFYUI_DIR}/models/ipadapter"     "${IPADAPTER_MODELS[@]}"
    provisioning_get_files "${COMFYUI_DIR}/models/loras"         "${FACEID_LORAS[@]}"
    provisioning_get_files "${COMFYUI_DIR}/models/controlnet"    "${CONTROLNET_MODELS[@]}"

    # CLIP Vision — generic имя на HuggingFace, нужен rename
    download_and_rename \
        "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors" \
        "${COMFYUI_DIR}/models/clip_vision" \
        "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"

    echo ""
    echo "Brand Model I2I настроен → Starting ComfyUI..."
    echo ""
}

function download_and_rename() {
    local url="$1"
    local dir="$2"
    local filename="$3"

    mkdir -p "$dir"
    local target="${dir}/${filename}"

    if [[ -f "$target" ]]; then
        echo "Уже существует: $target"
        return
    fi

    echo "→ Скачиваем ${filename}..."

    local auth_header=""
    if [[ -n "$HF_TOKEN" && "$url" =~ huggingface\.co ]]; then
        auth_header="--header=Authorization: Bearer $HF_TOKEN"
    fi

    wget $auth_header --show-progress -e dotbytes=4M -O "$target" "$url" || echo " [!] Download failed: $url"
    echo ""
}

function provisioning_clone_comfyui() {
    if [[ ! -d "${COMFYUI_DIR}" ]]; then
        echo "Клонируем ComfyUI..."
        git clone https://github.com/comfyanonymous/ComfyUI.git "${COMFYUI_DIR}"
    fi
    cd "${COMFYUI_DIR}"
}

function provisioning_install_base_reqs() {
    if [[ -f requirements.txt ]]; then
        echo "Устанавливаем base requirements..."
        pip install --no-cache-dir -r requirements.txt
    fi
}

function provisioning_get_apt_packages() {
    if [[ ${#APT_PACKAGES[@]} -gt 0 ]]; then
        echo "Устанавливаем apt packages..."
        sudo apt update && sudo apt install -y "${APT_PACKAGES[@]}"
    fi
}

function provisioning_get_pip_packages() {
    if [[ ${#PIP_PACKAGES[@]} -gt 0 ]]; then
        echo "Устанавливаем extra pip packages..."
        pip install --no-cache-dir "${PIP_PACKAGES[@]}"
    fi
}

function provisioning_get_nodes() {
    mkdir -p "${COMFYUI_DIR}/custom_nodes"
    cd "${COMFYUI_DIR}/custom_nodes"

    for repo in "${NODES[@]}"; do
        dir="${repo##*/}"
        path="./${dir}"

        if [[ -d "$path" ]]; then
            echo "Updating node: $dir"
            (cd "$path" && git pull --ff-only 2>/dev/null || { git fetch && git reset --hard origin/main; })
        else
            echo "Cloning node: $dir"
            git clone "$repo" "$path" --recursive || echo " [!] Clone failed: $repo"
        fi

        requirements="${path}/requirements.txt"
        if [[ -f "$requirements" ]]; then
            echo "Installing deps for $dir..."
            pip install --no-cache-dir -r "$requirements" || echo " [!] pip requirements failed for $dir"
        fi
    done
}

function provisioning_get_files() {
    if [[ $# -lt 2 ]]; then return; fi
    local dir="$1"
    shift
    local files=("$@")

    mkdir -p "$dir"
    echo "Скачивание ${#files[@]} file(s) → $dir..."

    for url in "${files[@]}"; do
        echo "→ $url"
        local auth_header=""
        if [[ -n "$HF_TOKEN" && "$url" =~ huggingface\.co ]]; then
            auth_header="--header=Authorization: Bearer $HF_TOKEN"
        elif [[ -n "$CIVITAI_TOKEN" && "$url" =~ civitai\.com ]]; then
            auth_header="--header=Authorization: Bearer $CIVITAI_TOKEN"
        fi

        wget $auth_header -nc --content-disposition --show-progress -e dotbytes=4M -P "$dir" "$url" || echo " [!] Download failed: $url"
        echo ""
    done
}

# Запуск provisioning если не отключен
if [[ ! -f /.noprovisioning ]]; then
    provisioning_start
fi

# Запуск ComfyUI
echo "=== Запускаем ComfyUI: Brand Model I2I ==="
cd "${COMFYUI_DIR}"
python main.py --listen 0.0.0.0 --port 8188
