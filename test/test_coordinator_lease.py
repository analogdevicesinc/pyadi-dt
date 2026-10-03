"""Exercise coordinator ownership with a fake client, never hardware."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/coordinator-lease.py"


@pytest.fixture
def lease(tmp_path):
    client = tmp_path / "client"
    client.write_text(f'''#!{sys.executable}
import json, os, sys, time
with open(os.environ["CALLS"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if "reserve" in sys.argv:
    print("export LG_TOKEN=owned-token")
if "wait" in sys.argv and os.environ.get("MODE") == "timeout":
    time.sleep(3)
if "acquire" in sys.argv and os.environ.get("MODE") == "acquire-fail":
    sys.exit(1)
if "release" in sys.argv and os.environ.get("MODE") == "release-fail":
    sys.exit(1)
''')
    client.chmod(0o755)
    env = dict(os.environ, LGCLIENT=str(client), LG_COORDINATOR="mock:20408",
               LG_PLACE="test-place", WAIT_MIN="0.01", LEASE_STATE=str(tmp_path / "lease.json"),
               CALLS=str(tmp_path / "calls"))
    return env


def run(env, action):
    return subprocess.run([sys.executable, str(SCRIPT), action], env=env,
                          capture_output=True, text=True)


def calls(env):
    path = Path(env["CALLS"])
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_preparation_failure_cleanup_does_nothing(lease):
    # Execute the actual workflow cleanup body without having acquired anything.
    workflow = yaml.safe_load((ROOT / ".github/workflows/hw-matrix.yml").read_text())
    for job in ("hw-dynamic", "hw-coord"):
        step = next(s for s in workflow["jobs"][job]["steps"]
                    if s.get("name") == "Release coordinator place")
        result = subprocess.run(["bash", "-e", "-c", step["run"]], env=lease,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert run(lease, "cleanup").returncode == 0
    assert calls(lease) == []


@pytest.mark.parametrize("mode", ["timeout", "acquire-fail"])
def test_partial_acquisition_cancels_only_owned_token(lease, mode):
    lease["MODE"] = mode
    assert run(lease, "acquire").returncode != 0
    assert json.loads(Path(lease["LEASE_STATE"]).read_text())["token"] == "owned-token"
    assert run(lease, "cleanup").returncode == 0
    assert calls(lease)[-1] == ["-x", "mock:20408", "cancel-reservation", "owned-token"]
    assert not any("release" in call or "--all" in call for call in calls(lease))


@pytest.mark.parametrize("mode, expected", [("", 0), ("release-fail", 1)])
def test_successful_acquisition_release_and_cleanup_failure(lease, mode, expected):
    assert run(lease, "acquire").returncode == 0
    lease["MODE"] = mode
    assert run(lease, "cleanup").returncode == expected
    assert calls(lease)[-2:] == [
        ["-x", "mock:20408", "-p", "+owned-token", "release"],
        ["-x", "mock:20408", "cancel-reservation", "owned-token"],
    ]
