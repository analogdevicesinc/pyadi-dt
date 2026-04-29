#!/bin/bash
# deploy.sh — push install.sh + unit to one or more hw-nodes and run it.
#
# Two modes:
#
#   1. Manifest mode (default).  Hosts come from a manifest file
#      (default: nodes.conf next to this script).  Useful for
#      deploying to a known set of lab nodes.
#
#        ./deploy.sh                  # every host in the manifest
#        ./deploy.sh bq nemo          # subset (must be in manifest)
#        ./deploy.sh --manifest PATH  # use a different manifest
#
#   2. Ad-hoc mode.  Specify a single host directly on the command
#      line — no manifest needed.  Useful for one-off deploys before
#      you've added the host to the manifest.
#
#        ./deploy.sh --node mini2 \
#            --yaml /home/me/lg_mini2_exporter.yaml \
#            --bin  /home/me/.local/bin/labgrid-exporter
#
# Common flags:
#   --dry-run, -n                 Print commands without running them.
#   -h, --help                    Show this help.
#
# Manifest-mode flags:
#   --manifest PATH               Manifest file (default: nodes.conf
#                                 next to deploy.sh, override via the
#                                 LG_DEPLOY_MANIFEST env var).
#
# Ad-hoc-mode flags:
#   --node HOST                   ssh-resolvable host to deploy to.
#   --yaml PATH                   Source yaml on the host.
#   --bin PATH                    Path to labgrid-exporter on the host
#                                 (forwarded as --bin to install.sh).
#                                 Optional — install.sh auto-detects
#                                 if labgrid-exporter is on the sudo
#                                 login PATH.
#   --                            Everything after -- is forwarded to
#                                 install.sh as extra arguments
#                                 (e.g. --coordinator HOST:PORT).
#
# Manifest format (pipe-separated, blank lines and "#" comments allowed):
#   host | yaml-path-on-host | extra-install.sh-args
#
# deploy.sh always passes --stop-manual --force-yaml to install.sh.
# Each host prompts once for the sudo password.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DEFAULT_MANIFEST="$SCRIPT_DIR/nodes.conf"

DRY=0
SELECTED=()
COMMON_ARGS=("--stop-manual" "--force-yaml")
MANIFEST="${LG_DEPLOY_MANIFEST:-$DEFAULT_MANIFEST}"

# Ad-hoc mode state.
ADHOC_NODE=""
ADHOC_YAML=""
ADHOC_BIN=""
ADHOC_PASSTHROUGH=()

usage() { sed -n '2,/^$/p' "$0"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run|-n) DRY=1; shift ;;
        --manifest)   MANIFEST="$2"; shift 2 ;;
        --node)       ADHOC_NODE="$2"; shift 2 ;;
        --yaml)       ADHOC_YAML="$2"; shift 2 ;;
        --bin)        ADHOC_BIN="$2"; shift 2 ;;
        --) shift; ADHOC_PASSTHROUGH=("$@"); break ;;
        -h|--help)    usage; exit 0 ;;
        -*)
            echo "ERROR: unknown option $1" >&2
            exit 1
            ;;
        *) SELECTED+=("$1"); shift ;;
    esac
done

# Mode detection: --node selects ad-hoc mode.
ADHOC=0
if [ -n "$ADHOC_NODE" ] || [ -n "$ADHOC_YAML" ]; then
    ADHOC=1
fi

if [ "$ADHOC" -eq 1 ]; then
    if [ -z "$ADHOC_NODE" ] || [ -z "$ADHOC_YAML" ]; then
        echo "ERROR: ad-hoc mode requires both --node and --yaml" >&2
        exit 1
    fi
    if [ ${#SELECTED[@]} -gt 0 ]; then
        echo "ERROR: positional host filters and --node are mutually exclusive" >&2
        echo "       (positional args are for manifest mode)" >&2
        exit 1
    fi

    extra=""
    if [ -n "$ADHOC_BIN" ]; then
        extra="--bin $ADHOC_BIN"
    fi
    if [ ${#ADHOC_PASSTHROUGH[@]} -gt 0 ]; then
        extra="$extra ${ADHOC_PASSTHROUGH[*]}"
    fi
    NODES=("$ADHOC_NODE|$ADHOC_YAML|$extra")
else
    if [ ! -r "$MANIFEST" ]; then
        echo "ERROR: manifest not found at $MANIFEST" >&2
        if [ -r "$SCRIPT_DIR/nodes.conf.example" ]; then
            echo "       Either:" >&2
            echo "         (a) copy nodes.conf.example to nodes.conf and edit it:" >&2
            echo "             cp $SCRIPT_DIR/nodes.conf.example $SCRIPT_DIR/nodes.conf" >&2
            echo "         (b) deploy a single host without a manifest:" >&2
            echo "             $0 --node HOST --yaml /path/to/exporter.yaml [--bin /path/to/labgrid-exporter]" >&2
        fi
        exit 1
    fi

    # Parse the manifest.  Each entry is "host|yaml|extra" with surrounding
    # whitespace trimmed from each field.
    NODES=()
    while IFS= read -r line || [ -n "$line" ]; do
        # Strip comments after '#' and trim outer whitespace.
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [ -z "$line" ] && continue

        IFS='|' read -r host yaml extra <<<"$line"
        host="${host#"${host%%[![:space:]]*}"}";  host="${host%"${host##*[![:space:]]}"}"
        yaml="${yaml#"${yaml%%[![:space:]]*}"}";  yaml="${yaml%"${yaml##*[![:space:]]}"}"
        extra="${extra#"${extra%%[![:space:]]*}"}"; extra="${extra%"${extra##*[![:space:]]}"}"

        if [ -z "$host" ] || [ -z "$yaml" ]; then
            echo "ERROR: malformed manifest line: $line" >&2
            echo "       Expected: host | yaml-path | [extra args]" >&2
            exit 1
        fi
        NODES+=("$host|$yaml|$extra")
    done < "$MANIFEST"

    if [ ${#NODES[@]} -eq 0 ]; then
        echo "ERROR: manifest $MANIFEST has no entries" >&2
        exit 1
    fi

    # Build the list of known hosts for validation.
    KNOWN_HOSTS=()
    for entry in "${NODES[@]}"; do
        IFS='|' read -r host _ _ <<<"$entry"
        KNOWN_HOSTS+=("$host")
    done

    # Error out on any selected host that isn't in the manifest — easier to
    # spot a typo than to silently do nothing.
    for s in "${SELECTED[@]}"; do
        found=0
        for h in "${KNOWN_HOSTS[@]}"; do
            if [ "$s" = "$h" ]; then found=1; break; fi
        done
        if [ "$found" -eq 0 ]; then
            echo "ERROR: '$s' is not in the manifest." >&2
            echo "       Known hosts: ${KNOWN_HOSTS[*]}" >&2
            echo "       Manifest:    $MANIFEST" >&2
            echo "       For a one-off deploy without the manifest, use:" >&2
            echo "         $0 --node $s --yaml /path/to/exporter.yaml [--bin ...]" >&2
            exit 1
        fi
    done
fi

run() {
    printf '+ %s\n' "$*"
    if [ "$DRY" -eq 0 ]; then
        "$@"
    fi
}

deploy_one() {
    local host=$1 yaml=$2 extra=$3
    echo
    echo "===== $host ====="
    run rsync -av "$SCRIPT_DIR/" "$host:~/labgrid-exporter-install/"
    # shellcheck disable=SC2086
    run ssh -t "$host" "sudo ~/labgrid-exporter-install/install.sh $yaml ${COMMON_ARGS[*]} $extra"
}

for entry in "${NODES[@]}"; do
    IFS='|' read -r host yaml extra <<<"$entry"

    if [ "$ADHOC" -eq 0 ] && [ ${#SELECTED[@]} -gt 0 ]; then
        skip=1
        for s in "${SELECTED[@]}"; do
            if [ "$s" = "$host" ]; then skip=0; break; fi
        done
        [ "$skip" -eq 1 ] && continue
    fi

    deploy_one "$host" "$yaml" "$extra"
done

echo
echo "Done.  Verify with:"
echo "   labgrid-client -x <coordinator>:20408 places"
