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
if "acquire" in sys.argv and os.environ.get("MODE") == "interrupt-acquire":
    import signal
    os.kill(os.getppid(), signal.SIGTERM)
if "acquire" in sys.argv and os.environ.get("MODE") == "acquire-fail":
    sys.exit(1)
if "release" in sys.argv and os.environ.get("MODE") == "release-fail":
    sys.exit(1)
if "release" in sys.argv and os.environ.get("MODE") == "acquire-fail":
    print("labgrid-client: place test-place is not acquired", file=sys.stderr)
    sys.exit(1)
if "cancel-reservation" in sys.argv and os.environ.get("MODE") == "cancel-fail":
    print("owned-token", file=sys.stderr)
    sys.exit(1)
assert "LG_ENV" not in os.environ
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
    result = run(lease, "acquire")
    assert result.returncode != 0
    assert "owned-token" not in result.stdout + result.stderr
    assert json.loads(Path(lease["LEASE_STATE"]).read_text())["token"] == "owned-token"
    assert run(lease, "cleanup").returncode == 0
    assert calls(lease)[-1] == ["-x", "mock:20408", "cancel-reservation", "owned-token"]
    assert not any("--all" in call for call in calls(lease))
    assert any("release" in call for call in calls(lease)) == (mode == "acquire-fail")


@pytest.mark.parametrize("mode, expected", [("", 0), ("release-fail", 1)])
def test_successful_acquisition_release_and_cleanup_failure(lease, mode, expected):
    assert run(lease, "acquire").returncode == 0
    lease["MODE"] = mode
    assert run(lease, "cleanup").returncode == expected
    if mode == "release-fail":
        assert "release" in calls(lease)[-1]
        assert Path(lease["LEASE_STATE"]).exists()
        assert not any("cancel-reservation" in call for call in calls(lease))
        return
    assert calls(lease)[-2:] == [
        ["-x", "mock:20408", "-p", "+owned-token", "release"],
        ["-x", "mock:20408", "cancel-reservation", "owned-token"],
    ]


def test_private_state_and_inherited_environment(lease):
    lease["LG_ENV"] = "/must-not-load-other-places.yaml"
    assert run(lease, "acquire").returncode == 0
    state = Path(lease["LEASE_STATE"])
    assert state.stat().st_mode & 0o777 == 0o600
    assert run(lease, "cleanup").returncode == 0
    assert not state.exists()


def test_cancel_failure_is_private_and_retryable(lease):
    assert run(lease, "acquire").returncode == 0
    lease["MODE"] = "cancel-fail"
    result = run(lease, "cleanup")
    assert result.returncode == 1
    assert "owned-token" not in result.stdout + result.stderr
    assert not json.loads(Path(lease["LEASE_STATE"]).read_text())["acquired"]
    lease["MODE"] = ""
    assert run(lease, "cleanup").returncode == 0
    assert sum("release" in call for call in calls(lease)) == 1


def test_interrupted_acquire_still_releases_own_allocation(lease):
    lease["MODE"] = "interrupt-acquire"
    assert run(lease, "acquire").returncode != 0
    assert json.loads(Path(lease["LEASE_STATE"]).read_text())["acquired"]
    assert run(lease, "cleanup").returncode == 0
    assert calls(lease)[-2:] == [
        ["-x", "mock:20408", "-p", "+owned-token", "release"],
        ["-x", "mock:20408", "cancel-reservation", "owned-token"],
    ]


def test_unknown_reservation_outcome_fails_closed(lease):
    Path(lease["LEASE_STATE"]).write_text("null")
    assert run(lease, "cleanup").returncode == 1
    assert calls(lease) == []


def test_atomic_update_preserves_previous_state_on_failure(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("coordinator_lease", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = tmp_path / "state.json"
    module.save(state, {"acquired": False})

    def fail_replace(*args):
        raise OSError("injected replacement failure")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError):
        module.save(state, {"acquired": True})
    assert json.loads(state.read_text()) == {"acquired": False}
    assert list(tmp_path.iterdir()) == [state]
