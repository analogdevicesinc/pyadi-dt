"""Acquire and clean up only this job's labgrid reservation and place."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


def main():
    state = Path(os.environ["LEASE_STATE"])
    client = [os.path.expanduser(os.path.expandvars(os.environ["LGCLIENT"])),
              "-x", os.environ["LG_COORDINATOR"]]
    if sys.argv[1] == "cleanup":
        if not state.exists():
            return 0
        lease = json.loads(state.read_text())
        failed = False
        if lease["acquired"]:
            result = subprocess.run(client + ["-p", "+" + lease["token"], "release"])
            failed |= result.returncode != 0
        result = subprocess.run(client + ["cancel-reservation", lease["token"]])
        failed |= result.returncode != 0
        if not failed:
            state.unlink()
        return int(failed)

    # Never replace another invocation's ownership record.
    state.parent.mkdir(parents=True, exist_ok=True)
    with state.open("x") as record:
        record.write("null")
    result = subprocess.run(
        client + ["reserve", "--shell", "name=" + os.environ["LG_PLACE"]],
        capture_output=True, text=True,
    )
    match = re.search(r"^export LG_TOKEN=([A-Za-z0-9_-]+)$", result.stdout, re.M)
    if match is None:
        state.unlink()
        print(result.stdout + result.stderr, file=sys.stderr)
        return result.returncode or 1
    lease = {"token": match[1], "acquired": False}
    state.write_text(json.dumps(lease))
    if result.returncode:
        return result.returncode
    # Persist ownership before waiting, so a timeout can cancel this token only.
    subprocess.run(client + ["wait", lease["token"]], check=True,
                   timeout=float(os.environ["WAIT_MIN"]) * 60)
    subprocess.run(client + ["-p", "+" + lease["token"], "acquire"], check=True)
    lease["acquired"] = True
    state.write_text(json.dumps(lease))
    return 0


if __name__ == "__main__":
    sys.exit(main())
