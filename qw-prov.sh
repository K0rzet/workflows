#!/bin/bash
set -e
source /venv/main/bin/activate

WORKSPACE=${WORKSPACE:-/workspace}
COMFYUI_DIR="${WORKSPACE}/ComfyUI"

echo "=== ComfyUI Qwen Workflows Provision ==="

###############################################################################
#  Воркфлоу, которые покрываются этим скриптом:
#
#  WF1 — Posture Migration (NSFW)
#  WF2 — Qwen Image Edit + Save Latent (NSFW)
#  WF3 — Enhanced Qwen Image Edit 2511 / Clothing Change
#
###############################################################################

APT_PACKAGES=()
PIP_PACKAGES=(
    "onnxruntime-gpu"   # для controlnet_aux и прочих onnx-зависимостей
)

# ─────────────────────────── CUSTOM NODES ───────────────────────────
NODES=(
    # --- общие / базовые ---
    "https://github.com/kijai/ComfyUI-KJNodes"                   # ImageConcanate, ImageConcatMulti
    "https://github.com/pythongosssss/ComfyUI-Custom-Scripts"     # StringFunction|pysssss, MarkdownNote
    "https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes"     # CR Text, CR Image Input Switch, CR Prompt Text
    "https://github.com/rgthree/rgthree-comfy"                    # SetNode, GetNode
    "https://github.com/chflame163/ComfyUI_LayerStyle"            # LayerUtility: ImageScaleByAspectRatio V2, PurgeVRAM V2

    # --- WF1: Posture Migration ---
    "https://github.com/Fannovel16/comfyui_controlnet_aux"        # AIO_Preprocessor
    "https://github.com/yolain/ComfyUI-Easy-Use"                  # easy showAnything
    "https://github.com/jamesWalker55/comfyui-various"            # JWFloat

    # --- WF3: Enhanced Qwen Edit 2511 / Clothing ---
    "https://github.com/lrzjason/Comfyui-QwenEditUtils"           # QwenEdit* ноды, TextEncodeQwenImageEditPlusCustom
    "https://github.com/chrisgoringe/cg-use-everywhere"           # Anything Everywhere
    "https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler"       # SeedVR2 апскейл
    "https://github.com/ali-vilab/ACE_plus"                       # FluxKontextMultiReferenceLatentMethod
)

# ─────────────────────── TEXT ENCODERS (shared) ─────────────────────
TEXT_ENCODERS=(
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
)

# ─────────────────────── VAE (shared) ───────────────────────────────
VAE_MODELS=(
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors"
)

# ─────────────────────── DIFFUSION MODELS ───────────────────────────
#  WF1 использует qwen_image_edit_2509_fp8_e4m3fn.safetensors
#       (это переименованный qwen_image_edit_fp8_e4m3fn.safetensors)
#  WF2 использует qwen_image_edit_bf16.safetensors
#  WF3 использует qwen_image_edit_2511_bf16.safetensors
#                 + qwen_image_edit_fp8_e4m3fn.safetensors
DIFFUSION_MODELS=(
    "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_fp8_e4m3fn.safetensors"
    "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_bf16.safetensors"
    "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_bf16.safetensors"
)

# ─────────────────────── LORAS (публичные) ──────────────────────────
LORAS=(
    # WF1: Posture Migration
    "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning-8steps-V2.0-bf16.safetensors"

    # WF2: Image Edit + Save Latent
    "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning-8steps-V1.1.safetensors"

    # WF3: Enhanced 2511 / Clothing
    "https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-fp32.safetensors"
    "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors"
    "https://huggingface.co/dong625/kontext_loras/blob/main/clothes_remover_v0.safetensors"
    "https://huggingface.co/wiikoo/Qwen-lora-nsfw/blob/main/loras/p0ssy_lora_v1.safetensors"
    "https://huggingface.co/wiikoo/Qwen-lora-nsfw/blob/main/loras/Qwen_Nsfw_Body_V14-10K.safetensors"
)

# ─────────────────────── SEEDVR2 (WF3 upscaler) ────────────────────
SEEDVR2_MODELS=(
    "https://huggingface.co/cmeka/SeedVR2-GGUF/resolve/main/seedvr2_ema_7b-Q8_0.gguf"
    "https://huggingface.co/numz/SeedVR2_comfyUI/resolve/main/ema_vae_fp16.safetensors"
)

###############################################################################
###  NSFW / кастомные LoRA — нужно положить ВРУЧНУЮ в models/loras:
###
###  WF2:  remove clothes3000.safetensors
###  WF3:  QWEN-P0ssy_lora_v1.safetensors
###
###  Эти файлы не распространяются публично. Положите их сами перед
###  запуском соответствующих воркфлоу.
###############################################################################

###############################################################################
###  НЕОБЯЗАТЕЛЬНЫЕ / специфичные ноды:
###
###  TT_img_enc  — шифрование изображений (WF1). Можно убрать из
###                воркфлоу, соединив VAEDecode → SaveImage напрямую.
###
###  RH_Captioner — автокэпшен (WF1). Если нужен, попробуйте:
###                 git clone https://github.com/RunningHub/ComfyUI-RH-Utils
###############################################################################

### ─────────────────────────────────────────────
### DO NOT EDIT BELOW UNLESS YOU KNOW WHAT YOU ARE DOING
### ─────────────────────────────────────────────

function provisioning_start() {
    echo ""
    echo "##############################################"
    echo "#  Qwen Workflows Provision                  #"
    echo "#  3-in-1: Posture / Edit / Clothing         #"
    echo "##############################################"
    echo ""

    provisioning_get_apt_packages
    provisioning_clone_comfyui
    provisioning_install_base_reqs
    provisioning_get_nodes
    provisioning_get_pip_packages

    # --- Модели ---
    provisioning_get_files "${COMFYUI_DIR}/models/text_encoders"      "${TEXT_ENCODERS[@]}"
    provisioning_get_files "${COMFYUI_DIR}/models/vae"                "${VAE_MODELS[@]}"
    provisioning_get_files "${COMFYUI_DIR}/models/diffusion_models"   "${DIFFUSION_MODELS[@]}"
    provisioning_get_files "${COMFYUI_DIR}/models/loras"              "${LORAS[@]}"
    provisioning_get_files "${COMFYUI_DIR}/models/SEEDVR2"            "${SEEDVR2_MODELS[@]}"

    # --- Ренеймы для WF1 (2509-версия = переименованный fp8) ---
    provisioning_rename_models

    echo ""
    echo "Provision завершён → Starting ComfyUI..."
    echo ""
}

function provisioning_rename_models() {
    local dm_dir="${COMFYUI_DIR}/models/diffusion_models"
    local lora_dir="${COMFYUI_DIR}/models/loras"

    # WF1 ожидает файл с именем qwen_image_edit_2509_fp8_e4m3fn.safetensors
    local src="${dm_dir}/qwen_image_edit_fp8_e4m3fn.safetensors"
    local dst="${dm_dir}/qwen_image_edit_2509_fp8_e4m3fn.safetensors"
    if [[ -f "$src" && ! -f "$dst" ]]; then
        echo "Создаю симлинк: $(basename "$dst") → $(basename "$src")"
        ln -sf "$(basename "$src")" "$dst"
    fi

    # WF1 ожидает пробел в имени лоры (V2.0 bf16 вместо V2.0-bf16)
    local lsrc="${lora_dir}/Qwen-Image-Lightning-8steps-V2.0-bf16.safetensors"
    local ldst="${lora_dir}/Qwen-Image-Lightning-8steps-V2.0 bf16.safetensors"
    if [[ -f "$lsrc" && ! -f "$ldst" ]]; then
        echo "Создаю симлинк: $(basename "$ldst") → $(basename "$lsrc")"
        ln -sf "Qwen-Image-Lightning-8steps-V2.0-bf16.safetensors" "$ldst"
    fi
}

function provisioning_clone_comfyui() {
    if [[ ! -d "${COMFYUI_DIR}" ]]; then
        echo "Клонирую ComfyUI..."
        git clone https://github.com/comfyanonymous/ComfyUI.git "${COMFYUI_DIR}"
    fi
    cd "${COMFYUI_DIR}"
}

function provisioning_install_base_reqs() {
    if [[ -f requirements.txt ]]; then
        echo "Устанавливаю base requirements..."
        pip install --no-cache-dir -r requirements.txt
    fi
}

function provisioning_get_apt_packages() {
    if [[ ${#APT_PACKAGES[@]} -gt 0 ]]; then
        echo "Устанавливаю apt packages..."
        sudo apt update && sudo apt install -y "${APT_PACKAGES[@]}"
    fi
}

function provisioning_get_pip_packages() {
    if [[ ${#PIP_PACKAGES[@]} -gt 0 ]]; then
        echo "Устанавливаю extra pip packages..."
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
            echo "Обновляю ноду: $dir"
            (cd "$path" && git pull --ff-only 2>/dev/null || { git fetch && git reset --hard origin/main; })
        else
            echo "Клонирую ноду: $dir"
            git clone "$repo" "$path" --recursive || echo " [!] Clone failed: $repo"
        fi

        requirements="${path}/requirements.txt"
        if [[ -f "$requirements" ]]; then
            echo "Устанавливаю deps для $dir..."
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
    echo "Скачиваю ${#files[@]} файл(ов) → $dir..."

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

# ─── Запуск ────────────────────────────────────────────────────────
if [[ ! -f /.noprovisioning ]]; then
    provisioning_start
fi

echo "=== Запускаю ComfyUI ==="
cd "${COMFYUI_DIR}"
python main.py --listen 0.0.0.0 --port 8188
