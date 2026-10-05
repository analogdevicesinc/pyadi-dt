#!/usr/bin/env bash
# Run in the dynamic matrix BEFORE acquire-place, never under a board lease.
set -euo pipefail
: "${VENV_DIR:?hardware venv required}"
: "${BOARD:?board required}" "${CARRIER:?carrier required}"
case "$BOARD-$CARRIER" in
    *[!a-zA-Z0-9_-]*) echo 'Invalid hardware configuration name' >&2; exit 1 ;;
esac
config="${ADIDT_HARDWARE_CONFIG_DIR:-$HOME/.config/pyadi-dt/hardware}/$BOARD-$CARRIER.env"
if [[ -f "$config" ]]; then source "$config"; fi
case "$CARRIER" in
    zc706) platform=zynq ;;
    zcu102) platform=zynqmp ;;
    *) exit 0 ;; # Fabric and standalone production-JTAG flows own their kernels.
esac
# Validate before constructing paths; never normalize a misspelled release.
export ADIDT_CIM_RELEASE="${ADIDT_CIM_RELEASE-2023_R2}"
case "$ADIDT_CIM_RELEASE" in
    2023_R2|2026-R1) ;;
    *) echo "Unsupported CIM release: $ADIDT_CIM_RELEASE" >&2; exit 1 ;;
esac
# An ordinary CIM image is NOT a modular runtime-overlay kernel.
shopt -s nullglob
ordinary=(test/hw/*"${BOARD}"*"${CARRIER}"*_hw.py)
overlays=(test/hw/xsa/test_*"${BOARD}"*"${CARRIER}"*_overlay.py)
image_var="ADIDT_KERNEL_IMAGE_${platform^^}"
overlay_var="ADIDT_OVERLAY_KERNEL_IMAGE_${platform^^}"
disabled="${ADI_XSA_BUILD_KERNEL:-1}"
if (( ${#overlays[@]} )) && [[ "${disabled,,}" != 0 && "${disabled,,}" != false && "${disabled,,}" != no ]]; then
    overlay_image="${!overlay_var:-${!image_var:-}}"
    if [[ ! -s "$overlay_image" ]]; then
        echo "Runtime overlays require $overlay_var (or a qualified $image_var) and matching modules; stock CIM images cannot replace them" >&2
        exit 1
    fi
fi
if (( ! ${#ordinary[@]} )); then exit 0; fi
# Avoid ambient user tools shadowing GNU binutils. CIM can be an absolute path.
export PATH="$VENV_DIR/bin:/usr/bin:/bin"
exports=$(mktemp)
trap 'rm -f "$exports"' EXIT
"$VENV_DIR/bin/python" .github/scripts/prepare_cim_kernel.py \
    --release "$ADIDT_CIM_RELEASE" --platform "$platform" --cim "${ADIDT_CIM_EXECUTABLE:-cim}" \
    --source "${CIM_MANIFEST_SOURCE:-https://github.com/tfcollins/cim.git}" \
    --version "${CIM_MANIFEST_COMMIT:-29d715ff8de7f35aae66463864ce1631887e2198}" \
    --workspace "${RUNNER_TEMP:-/tmp}/adidt-cim-${ADIDT_CIM_RELEASE}-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$BOARD-$CARRIER" \
    > "$exports"
source "$exports"
# GitHub makes the validated selection available to the later test step.
if [[ -n "${GITHUB_ENV:-}" ]]; then
    printf 'ADIDT_CIM_RELEASE=%s\n' "$ADIDT_CIM_RELEASE" >> "$GITHUB_ENV"
fi
artifact_var="ADIDT_KERNEL_ARTIFACTS_${platform^^}"
if [[ -n "${GITHUB_ENV:-}" && -n "${!artifact_var:-}" ]]; then
    printf '%s=%s\n' "$artifact_var" "${!artifact_var}" >> "$GITHUB_ENV"
fi
