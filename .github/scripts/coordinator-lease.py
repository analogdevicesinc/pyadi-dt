"""Acquire and clean up only this job's labgrid reservation and place."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def save(state, lease):
    """Replace a complete record atomically, with owner-only permissions."""
    fd, name = tempfile.mkstemp(dir=state.parent, prefix=state.name + ".")
    try:
        with os.fdopen(fd, "w") as record:
            json.dump(lease, record)
            record.flush()
            os.fsync(record.fileno())
        os.replace(name, state)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def command(client, args, timeout=60.0):
    # Client diagnostics and exception representations can include the token.
    env = dict(os.environ)
    # LG_ENV makes acquire/release operate on all configured places in labgrid 26.
    for key in ("LG_ENV", "LG_STATE", "LG_INITIAL_STATE"):
        env.pop(key, None)
    return subprocess.run(client + args, capture_output=True, text=True,
                          timeout=timeout, env=env)


def main():
    state = Path(os.environ["LEASE_STATE"])
    client = [os.path.expanduser(os.path.expandvars(os.environ["LGCLIENT"])),
              "-x", os.environ["LG_COORDINATOR"]]
    if sys.argv[1] == "cleanup":
        if not state.exists():
            return 0
        lease = json.loads(state.read_text())
        if lease is None:
            # Reserve was interrupted before its token could be recorded.
            print("Reservation outcome unknown; ownership record retained", file=sys.stderr)
            return 1
        if lease["acquired"]:
            result = command(client, ["-p", "+" + lease["token"], "release"])
            # labgrid 26 reports this when acquire failed before taking ownership.
            not_acquired = f"labgrid-client: place {lease['place']} is not acquired"
            if result.returncode and not_acquired not in result.stderr.splitlines():
                print("Place release failed; reservation retained for retry", file=sys.stderr)
                return 1
            lease["acquired"] = False
            save(state, lease)
        result = command(client, ["cancel-reservation", lease["token"]])
        if result.returncode:
            print("Reservation cancellation failed; ownership record retained", file=sys.stderr)
            return 1
        state.unlink()
        return 0

    # Never replace another invocation's ownership record.
    state.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as record:
        record.write("null")
    result = command(client, ["reserve", "--shell", "name=" + os.environ["LG_PLACE"]])
    match = re.search(r"^export LG_TOKEN=([A-Za-z0-9_-]+)$", result.stdout, re.M)
    if match is None:
        print("Reservation outcome unknown; ownership record retained", file=sys.stderr)
        return result.returncode or 1
    lease = {"token": match[1], "acquired": False, "place": os.environ["LG_PLACE"]}
    save(state, lease)
    if result.returncode:
        return result.returncode
    result = command(client, ["wait", lease["token"]],
                     timeout=float(os.environ["WAIT_MIN"]) * 60)
    if result.returncode:
        print("Reservation wait failed", file=sys.stderr)
        return result.returncode
    # Write intent first: acquire may succeed remotely even if its reply is lost.
    # Only this token's allocation can be released, never an unowned place name.
    lease["acquired"] = True
    save(state, lease)
    result = command(client, ["-p", "+" + lease["token"], "acquire"])
    if result.returncode:
        print("Place acquisition failed; cleanup required", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt):
        print("Lease operation interrupted or failed; cleanup required", file=sys.stderr)
        sys.exit(1)
