#!/usr/bin/env bash
# Install the pyadi-dt CLI skill for Agent Skills-compatible tools.
set -euo pipefail

SKILL_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-all}"

install_skill() {
  local dest_dir="$1"
  local dest="${dest_dir}/pyadi-dt-cli"
  mkdir -p "${dest_dir}"

  if [[ -L "${dest}" ]]; then
    if [[ "$(readlink "${dest}")" == "${SKILL_SRC}" ]]; then
      echo "Already installed: ${dest} -> ${SKILL_SRC}"
      return
    fi
    echo "Updating symlink: ${dest}"
    rm "${dest}"
  elif [[ -e "${dest}" ]]; then
    echo "Error: ${dest} exists and is not a symlink; move it aside first." >&2
    return 1
  fi

  ln -s "${SKILL_SRC}" "${dest}"
  echo "Installed: ${dest} -> ${SKILL_SRC}"
}

case "${TARGET}" in
  all)
    install_skill "${HOME}/.agents/skills"
    install_skill "${HOME}/.claude/skills"
    ;;
  agents)
    install_skill "${HOME}/.agents/skills"
    ;;
  claude)
    install_skill "${HOME}/.claude/skills"
    ;;
  *)
    echo "Usage: $0 [all|agents|claude]" >&2
    exit 2
    ;;
esac

echo "Start a new agent session to load the skill."
