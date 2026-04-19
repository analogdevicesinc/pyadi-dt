#!/usr/bin/env bash
# Register self-hosted GitHub Actions runners on the hw-test nodes.
#
# Prereqs on the machine running this script:
#   - gh CLI authenticated with repo-admin scope on the target repo
#   - SSH key-based access as the target user on each host
#   - An interactive terminal (sudo will prompt for password per host)
#   - Local tools: gh, jq, ssh, scp, mktemp
#
# Usage:
#   ./register-hw-runners.sh                 # register all hosts
#   ./register-hw-runners.sh bq mini2        # register only listed hosts

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────
# CONFIGURATION — edit this section when adding / removing hw nodes.
# ─────────────────────────────────────────────────────────────────────
#
# HOSTS: one entry per runner to register.  Colon-separated fields:
#
#   alias : ssh_target : runner_label : runner_name : lg_direct_env
#
#   alias         Short name used in the CLI filter (e.g. './register-hw-runners.sh bq').
#                 Convention: match the labgrid place name.
#
#   ssh_target    Argument passed verbatim to `ssh` and `scp`.  Either a
#                 host in ~/.ssh/config or a raw IP/hostname.  Must use
#                 key-based auth — the script does not handle password prompts.
#
#   runner_label  Label the workflow uses in `runs-on: [self-hosted, <label>]`.
#                 Convention: `hw-<alias>` for per-board runners;
#                 `hw-coordinator` for the one runner that drives the
#                 RemotePlace `hw-coord` matrix legs.  Must match the
#                 `runner_label` column in `.github/hw-nodes.json`
#                 (except `hw-coordinator`, which is workflow-hardcoded).
#
#   runner_name   Name shown in the GitHub "Actions → Runners" UI and
#                 returned by `gh api /repos/.../actions/runners`.
#                 Keep it short and unique; the registration check at
#                 the end of this script looks runners up by this name.
#
#   lg_direct_env Absolute path ON THE REMOTE HOST to the node-local,
#                 uncommitted labgrid YAML that the hw-direct workflow
#                 leg uses (`LG_ENV=<this>`).  The script writes
#                 `LG_DIRECT_ENV=<path>` into `~/actions-runner/.env`
#                 so the runner service picks it up.  Leave EMPTY for
#                 the coordinator-host runner (hw-coord legs use the
#                 committed env_remote_*.yaml instead) and for any
#                 node where the direct YAML doesn't exist yet — the
#                 hw-direct job will then fail its explicit
#                 LG_DIRECT_ENV guard, which is the intended loud
#                 failure mode.
#
HOSTS=(
    "bq:bq:hw-bq:bq:/home/tcollins/dev/dt-fix/lg_adrv9371_zc706_tftp.yaml"
    "mini2:mini2:hw-mini2:mini2:"
    "nuc:nuc:hw-nuc:nuc:"
    "coordinator:10.0.0.41:hw-coordinator:coordinator:"
)

# Target repository (format: owner/repo) that the runners register against.
REPO="analogdevicesinc/pyadi-dt"

# Runner release used on every host.  Bump as newer releases ship:
# https://github.com/actions/runner/releases
RUNNER_VERSION="2.333.1"

# ─────────────────────────────────────────────────────────────────────
# End configuration — nothing below here should need edits.
# ─────────────────────────────────────────────────────────────────────

RUNNER_TARBALL="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_TARBALL}"

die() { echo "error: $*" >&2; exit 1; }

# Verify all required local tools are available before doing any work.
# (curl + tar run on the remote host, not here, so they're not listed.)
REQUIRED_TOOLS=(gh jq ssh scp mktemp)
missing=()
for tool in "${REQUIRED_TOOLS[@]}"; do
    command -v "$tool" >/dev/null || missing+=("$tool")
done
if ((${#missing[@]} > 0)); then
    die "missing required local tool(s): ${missing[*]}
    Install with your package manager (e.g. apt-get install ${missing[*]})."
fi

gh auth status -h github.com >/dev/null 2>&1 \
    || die "gh is not authenticated against github.com — run 'gh auth login' first"

# Confirm the token has enough scope to mint runner registration tokens.
if ! gh api "/repos/${REPO}" --jq '.permissions.admin' 2>/dev/null | grep -qx true; then
    die "the authenticated gh user lacks admin on ${REPO} — cannot mint registration tokens"
fi

# Filter HOSTS by CLI args if given.
if (($# > 0)); then
    FILTER=("$@")
    NEW_HOSTS=()
    for entry in "${HOSTS[@]}"; do
        alias="${entry%%:*}"
        for want in "${FILTER[@]}"; do
            if [[ "$alias" == "$want" ]]; then
                NEW_HOSTS+=("$entry")
                break
            fi
        done
    done
    ((${#NEW_HOSTS[@]} > 0)) || die "no hosts matched: ${FILTER[*]}"
    HOSTS=("${NEW_HOSTS[@]}")
fi

echo "Registering runners on:"
for e in "${HOSTS[@]}"; do printf '  - %s\n' "${e%%:*}"; done

REGISTERED_NAMES=()

# Build the remote-side script once; it's shipped to each host via scp and
# executed under a TTY so sudo can prompt for a password interactively.
REMOTE_SCRIPT=$(mktemp)
trap 'rm -f "$REMOTE_SCRIPT"' EXIT

cat > "$REMOTE_SCRIPT" <<'REMOTE'
#!/usr/bin/env bash
set -euo pipefail

: "${REPO:?REPO not set}"
: "${RUNNER_URL:?RUNNER_URL not set}"
: "${RUNNER_TARBALL:?RUNNER_TARBALL not set}"
: "${LABEL:?LABEL not set}"
: "${NAME:?NAME not set}"
: "${TOKEN:?TOKEN not set}"
LG_EXPORT_LINE="${LG_EXPORT_LINE:-}"

cd "$HOME"
mkdir -p actions-runner
cd actions-runner

if [[ ! -f "$RUNNER_TARBALL" ]]; then
    echo "-- downloading $RUNNER_TARBALL"
    curl --fail -sSL -o "$RUNNER_TARBALL" "$RUNNER_URL"
fi

if [[ ! -x ./config.sh ]]; then
    echo "-- extracting runner"
    tar xzf "$RUNNER_TARBALL"
fi

if [[ -f .runner ]]; then
    echo "-- runner already configured; removing old registration"
    ./config.sh remove --token "$TOKEN" || true
fi

echo "-- configuring runner (labels=self-hosted,$LABEL)"
./config.sh \
    --url "https://github.com/$REPO" \
    --token "$TOKEN" \
    --name "$NAME" \
    --labels "self-hosted,$LABEL" \
    --unattended --replace

if [[ -n "$LG_EXPORT_LINE" ]]; then
    touch .env
    grep -v '^LG_DIRECT_ENV=' .env > .env.new || true
    echo "$LG_EXPORT_LINE" >> .env.new
    mv .env.new .env
    echo "-- wrote .env: $LG_EXPORT_LINE"
fi

echo "-- installing service (sudo will prompt here)"
sudo ./svc.sh install "$USER"
sudo ./svc.sh start
sudo ./svc.sh status | head -5
REMOTE

for entry in "${HOSTS[@]}"; do
    IFS=':' read -r ALIAS SSH_TARGET LABEL NAME LG_DIRECT_ENV <<<"$entry"
    echo
    echo "=== $ALIAS ($SSH_TARGET) :: label=$LABEL ==="

    echo "-> minting registration token"
    TOKEN=$(gh api -X POST "/repos/${REPO}/actions/runners/registration-token" --jq .token)
    [[ -n "$TOKEN" ]] || die "failed to mint token for $ALIAS"

    LG_EXPORT_LINE=""
    if [[ -n "$LG_DIRECT_ENV" ]]; then
        LG_EXPORT_LINE="LG_DIRECT_ENV=${LG_DIRECT_ENV}"
    fi

    REMOTE_PATH="/tmp/register-hw-runner.$$.sh"
    echo "-> copying bootstrap to $SSH_TARGET:$REMOTE_PATH"
    scp -q "$REMOTE_SCRIPT" "$SSH_TARGET:$REMOTE_PATH"

    echo "-> remote install (sudo will prompt interactively)"
    # -t forces a TTY; stdin stays on the local terminal so sudo can prompt.
    # Env vars are prefixed on the remote command line, not piped via stdin.
    ssh -t \
        -o ControlMaster=no \
        -o ServerAliveInterval=30 \
        "$SSH_TARGET" \
        "REPO='$REPO' RUNNER_URL='$RUNNER_URL' RUNNER_TARBALL='$RUNNER_TARBALL' \
         LABEL='$LABEL' NAME='$NAME' LG_EXPORT_LINE='$LG_EXPORT_LINE' \
         TOKEN='$TOKEN' bash '$REMOTE_PATH'; rc=\$?; rm -f '$REMOTE_PATH'; exit \$rc"

    REGISTERED_NAMES+=("$NAME")
    echo "-- $ALIAS done"
done

echo
echo "All requested runners registered."
echo "Waiting 60s for them to phone home to GitHub..."

# Countdown so the user sees progress instead of a blank stall.
for i in $(seq 60 -5 5); do
    printf '  %ss remaining...\r' "$i"
    sleep 5
done
printf '                       \r'

echo "Querying runner status from GitHub:"
RUNNERS_JSON=$(gh api --paginate "/repos/${REPO}/actions/runners")

any_offline=0
for name in "${REGISTERED_NAMES[@]}"; do
    row=$(jq -r --arg n "$name" \
        '.runners[] | select(.name == $n) | "\(.status)\t\(.busy)\t\([.labels[].name] | join(","))"' \
        <<<"$RUNNERS_JSON" | head -1)
    if [[ -z "$row" ]]; then
        printf '  %-14s MISSING (not listed by GitHub)\n' "$name"
        any_offline=1
        continue
    fi
    IFS=$'\t' read -r status busy labels <<<"$row"
    if [[ "$status" == "online" ]]; then
        printf '  %-14s online  (busy=%s, labels=%s)\n' "$name" "$busy" "$labels"
    else
        printf '  %-14s %s   (labels=%s)\n' "$name" "$status" "$labels"
        any_offline=1
    fi
done

if (( any_offline )); then
    echo
    echo "One or more runners did not come online within 60s."
    echo "Troubleshoot on the affected host:"
    echo "  sudo ~/actions-runner/svc.sh status"
    echo "  journalctl -u 'actions.runner.*' -n 100 --no-pager"
    exit 1
fi

echo
echo "All registered runners are online."
