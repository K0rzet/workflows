#!/usr/bin/env bash
set -Eeuo pipefail

# Vast.ai one-URL bootstrap for the Comixes production bundle.
# By running this file you confirm that you have reviewed and accepted the
# WAI Illustrious, MiniMax H3 and MiniMax-H3-Image model licenses.
# This installs inference and comic workflows only; H3 training is not started.

export WORKSPACE="${WORKSPACE:-/workspace}"
export COMFYUI_DIR="${COMFYUI_DIR:-${WORKSPACE}/ComfyUI}"
export COMIXES_PROJECT="${COMIXES_PROJECT:-${WORKSPACE}/comixes-workflow}"
export COMIXES_REPO_URL="https://github.com/K0rzet/workflows.git"
export COMIXES_REF="${COMIXES_REF:-5e075704183a7611bb3163e7b6370f9366bb15ee}"

export PORT="${PORT:-8188}"
export GPU_PROFILE="${GPU_PROFILE:-auto}"
export INSTALL_WAI="${INSTALL_WAI:-1}"
export INSTALL_H3="${INSTALL_H3:-1}"
export INSTALL_H3_IMAGE="${INSTALL_H3_IMAGE:-1}"
export VERIFY_SHA256="${VERIFY_SHA256:-1}"
export INSTALL_SYSTEM_PACKAGES="${INSTALL_SYSTEM_PACKAGES:-1}"
export DISK_RESERVE_GIB="${DISK_RESERVE_GIB:-20}"
export PROVISION_ONLY="${PROVISION_ONLY:-0}"

export ACCEPT_WAI_LICENSE=1
export ACCEPT_MINIMAX_H3_LICENSE=1
export ACCEPT_MINIMAX_H3_IMAGE_LICENSE=1

BOOTSTRAP_URL="https://raw.githubusercontent.com/K0rzet/workflows/${COMIXES_REF}/cloud/comfyui/PROVISIONING_SCRIPT.sh"
TEMP_SCRIPT="$(mktemp --suffix=.sh)"
cleanup() { rm -f -- "${TEMP_SCRIPT}"; }
trap cleanup EXIT

echo "Comixes bundle: ${COMIXES_REF}"
echo "GPU profile: ${GPU_PROFILE}; ComfyUI port: ${PORT}"
curl --fail --location --retry 8 --retry-all-errors --output "${TEMP_SCRIPT}" "${BOOTSTRAP_URL}"
chmod 0700 "${TEMP_SCRIPT}"
bash "${TEMP_SCRIPT}"
