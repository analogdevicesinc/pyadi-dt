import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest

from adidt.xsa.sdtgen import SdtgenRunner
from adidt.xsa.exceptions import SdtgenNotFoundError, SdtgenError


def _help_result():
    r = MagicMock()
    r.returncode = 0
    r.stdout = "sdtgen -s <xsa> -d <outdir>"
    r.stderr = ""
    return r


def _ok_result():
    r = MagicMock()
    r.returncode = 0
    r.stdout = ""
    r.stderr = ""
    return r


def test_run_invokes_sdtgen_with_correct_args(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;")

    # New runner per test avoids module-level cache interference
    runner = SdtgenRunner()
    with patch("adidt.xsa.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]) as mock_run:
        result = runner.run(xsa, out_dir)

    # The second call is the actual sdtgen invocation
    sdtgen_call = mock_run.call_args_list[1]
    cmd = sdtgen_call[0][0]
    assert cmd[0] == "sdtgen"
    assert str(xsa) in cmd
    assert str(out_dir) in cmd
    assert result == out_dir / "system-top.dts"


def test_run_raises_not_found_when_binary_missing(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch("adidt.xsa.sdtgen.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SdtgenNotFoundError):
            runner.run(xsa, out_dir)


def test_run_raises_error_on_nonzero_exit(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    fail_result = MagicMock()
    fail_result.returncode = 1
    fail_result.stderr = "fatal: bad xsa"
    fail_result.stdout = ""

    runner = SdtgenRunner()
    with patch("adidt.xsa.sdtgen.subprocess.run", side_effect=[_help_result(), fail_result]):
        with pytest.raises(SdtgenError) as exc_info:
            runner.run(xsa, out_dir)
    assert "fatal: bad xsa" in exc_info.value.stderr


def test_run_raises_error_on_timeout(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch("adidt.xsa.sdtgen.subprocess.run", side_effect=[_help_result(), subprocess.TimeoutExpired("sdtgen", 5)]):
        with pytest.raises(SdtgenError, match="timed out"):
            runner.run(xsa, out_dir, timeout=5)


def test_run_scans_for_dts_when_system_top_absent(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "other_name.dts").write_text("/dts-v1/;")

    runner = SdtgenRunner()
    with patch("adidt.xsa.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]):
        result = runner.run(xsa, out_dir)
    assert result == out_dir / "other_name.dts"


def test_run_raises_error_when_no_dts_produced(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch("adidt.xsa.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]):
        with pytest.raises(SdtgenError, match=r"no \.dts output"):
            runner.run(xsa, out_dir)


def test_help_timeout_raises_sdtgen_error(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch("adidt.xsa.sdtgen.subprocess.run", side_effect=subprocess.TimeoutExpired("sdtgen", 10)):
        with pytest.raises(SdtgenError, match="timed out"):
            runner.run(xsa, out_dir)
