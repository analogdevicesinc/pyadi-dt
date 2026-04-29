#!/bin/bash
# install.sh — install the labgrid-exporter systemd service on this host.
#
# Convention:
#   - One exporter per host.
#   - Config lives at /etc/labgrid/exporter.yaml.
#   - Service is /etc/systemd/system/labgrid-exporter.service.
#   - Knobs (binary, coordinator, instance name) live in
#     /etc/default/labgrid-exporter.
#
# Usage:
#   sudo ./install.sh <source-yaml> [OPTIONS]
#
# Example:
#   sudo ./install.sh /home/tcollins/lg_adrv9009_zc706_tftp_exporter.yaml
#
# Options:
#   --name NAME           Exporter instance name registered with the
#                         coordinator (default: `hostname -s`).
#   --coordinator ADDR    host:port of the coordinator (default: 10.0.0.41:20408).
#   --user USER           Service runs as this user (default: $SUDO_USER).
#   --bin PATH            Path to labgrid-exporter (default: auto-detect on
#                         the service user's PATH).
#   --ser2net-path DIR    Prepend DIR to the service PATH (for ser2net).
#   --no-start            Install but don't enable/start the unit.
#   --force-yaml          Overwrite /etc/labgrid/exporter.yaml if it differs
#                         from the source.
#   --stop-manual         Kill any running manually-launched labgrid-exporter
#                         processes for the service user before starting the
#                         service.
#
# After install:
#   systemctl status labgrid-exporter
#   journalctl -u labgrid-exporter -f
#   sudo systemctl restart labgrid-exporter   # after editing the yaml
#
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: must run as root (use sudo)" >&2
    exit 1
fi

usage() { sed -n '2,/^$/p' "$0"; }

if [ $# -lt 1 ]; then
    usage >&2
    exit 1
fi

SRC_YAML="$1"
shift

NAME="$(hostname -s)"
COORDINATOR="10.0.0.41:20408"
SERVICE_USER="${SUDO_USER:-$USER}"
EXPORTER_BIN=""
SER2NET_PATH=""
START=1
FORCE_YAML=0
STOP_MANUAL=0

while [ $# -gt 0 ]; do
    case "$1" in
        --name)          NAME="$2"; shift 2 ;;
        --coordinator)   COORDINATOR="$2"; shift 2 ;;
        --user)          SERVICE_USER="$2"; shift 2 ;;
        --bin)           EXPORTER_BIN="$2"; shift 2 ;;
        --ser2net-path)  SER2NET_PATH="$2"; shift 2 ;;
        --no-start)      START=0; shift ;;
        --force-yaml)    FORCE_YAML=1; shift ;;
        --stop-manual)   STOP_MANUAL=1; shift ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "ERROR: unknown option $1" >&2; exit 1 ;;
    esac
done

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "ERROR: user '$SERVICE_USER' does not exist" >&2
    exit 1
fi

if [ -z "$EXPORTER_BIN" ]; then
    EXPORTER_BIN=$(sudo -u "$SERVICE_USER" -H bash -lc 'command -v labgrid-exporter' || true)
    if [ -z "$EXPORTER_BIN" ]; then
        echo "ERROR: labgrid-exporter not on PATH for user $SERVICE_USER." >&2
        echo "       Install it (e.g., 'uv tool install labgrid') or pass --bin PATH." >&2
        exit 1
    fi
fi
if [ ! -x "$EXPORTER_BIN" ]; then
    echo "ERROR: $EXPORTER_BIN is not executable" >&2
    exit 1
fi

SRC_ABS=$(readlink -f "$SRC_YAML")
if [ ! -r "$SRC_ABS" ]; then
    echo "ERROR: source yaml $SRC_ABS not readable" >&2
    exit 1
fi

CONF_DIR=/etc/labgrid
CONF_YAML=$CONF_DIR/exporter.yaml
ENV_DST=/etc/default/labgrid-exporter

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
UNIT_SRC="$SCRIPT_DIR/labgrid-exporter.service"
UNIT_DST=/etc/systemd/system/labgrid-exporter.service

if [ ! -f "$UNIT_SRC" ]; then
    echo "ERROR: unit template not found at $UNIT_SRC" >&2
    exit 1
fi

BASE_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
if [ -n "$SER2NET_PATH" ]; then
    SERVICE_PATH="$SER2NET_PATH:$BASE_PATH"
else
    SERVICE_PATH="$BASE_PATH"
fi

echo "Installing labgrid-exporter service:"
echo "   instance    : $NAME"
echo "   user        : $SERVICE_USER"
echo "   binary      : $EXPORTER_BIN"
echo "   coordinator : $COORDINATOR"
echo "   source yaml : $SRC_ABS"
echo "   config yaml : $CONF_YAML"
echo "   PATH        : $SERVICE_PATH"
echo

# Stop any leftover templated instances from the prior labgrid-exporter@ scheme.
mapfile -t OLD_TEMPLATED < <(systemctl list-units --no-pager --no-legend --all 'labgrid-exporter@*.service' 2>/dev/null | awk '{print $1}')
for u in "${OLD_TEMPLATED[@]}"; do
    [ -z "$u" ] && continue
    echo "Stopping legacy templated unit: $u"
    systemctl disable --now "$u" || true
done

# Stop any manually-launched exporter processes for the service user.
# The pattern requires "labgrid-exporter -c " to match (i.e., the binary
# name immediately followed by its -c flag) so that we don't match shells
# whose command line just contains the string "labgrid-exporter" (e.g. the
# parent ssh+sudo session that's running this very installer).
EXPORTER_PROC_RE='labgrid-exporter -c '
if [ "$STOP_MANUAL" -eq 1 ]; then
    PIDS=$(pgrep -u "$SERVICE_USER" -f "$EXPORTER_PROC_RE" || true)
    if [ -n "$PIDS" ]; then
        echo "Killing manual labgrid-exporter processes: $PIDS"
        # shellcheck disable=SC2086
        kill $PIDS || true
        sleep 2
        PIDS=$(pgrep -u "$SERVICE_USER" -f "$EXPORTER_PROC_RE" || true)
        if [ -n "$PIDS" ]; then
            echo "Sending SIGKILL to lingering processes: $PIDS"
            # shellcheck disable=SC2086
            kill -9 $PIDS || true
        fi
    fi
fi

# Install the yaml at the canonical location.
mkdir -p "$CONF_DIR"
chmod 755 "$CONF_DIR"
if [ -e "$CONF_YAML" ] && ! cmp -s "$SRC_ABS" "$CONF_YAML"; then
    if [ "$FORCE_YAML" -ne 1 ]; then
        echo "ERROR: $CONF_YAML already exists and differs from $SRC_ABS." >&2
        echo "       Re-run with --force-yaml to overwrite (a .bak copy is kept)." >&2
        exit 1
    fi
    cp -a "$CONF_YAML" "$CONF_YAML.bak.$(date +%Y%m%d-%H%M%S)"
fi
install -m 0644 "$SRC_ABS" "$CONF_YAML"

# Install the unit file.  The binary path is baked in literally because
# systemd does not expand environment variables in the ExecStart executable
# position — only in arguments.
sed -e "s|@SERVICE_USER@|$SERVICE_USER|g" \
    -e "s|@EXPORTER_BIN@|$EXPORTER_BIN|g" \
    "$UNIT_SRC" > "$UNIT_DST"
chmod 644 "$UNIT_DST"

# Install the env file.
cat > "$ENV_DST" <<EOF
# Generated by $(basename "$0") on $(date -Iseconds)
LG_COORDINATOR=$COORDINATOR
LG_EXPORTER_NAME=$NAME
LG_EXPORTER_YAML=$CONF_YAML
PATH=$SERVICE_PATH
EOF
chmod 644 "$ENV_DST"

systemctl daemon-reload

if [ "$START" -eq 1 ]; then
    systemctl enable --now labgrid-exporter
    sleep 2
    systemctl --no-pager --full status labgrid-exporter || true
else
    echo
    echo "Service installed but not started.  To start:"
    echo "   sudo systemctl enable --now labgrid-exporter"
fi
