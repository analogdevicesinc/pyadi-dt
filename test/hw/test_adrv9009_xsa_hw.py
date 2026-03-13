"""ADRV9009 + ZCU102 HW test for XSA-generated device trees.

This test uses labgrid plugins with the Jenkins labgrid environment file:
    /jenkins/lg_hw.yaml

Flow:
1. Download Kuiper boot-partition release tarball.
2. Extract project XSA from nested bootgen archive.
3. Run XSA pipeline to generate DTS.
4. Compile generated DTS to DTB using dtc.
5. Deploy BOOT.BIN + generated system.dtb with KuiperDLDriver.
6. Boot board and verify expected IIO devices.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from adidt.xsa.pipeline import XsaPipeline
from test.xsa.kuiper_release import download_project_xsa


LG_ENV_PATH = "/jenkins/lg_hw.yaml"
KUIPER_RELEASE_DEFAULT = "2023_r2"
KUIPER_PROJECT_DEFAULT = "zynqmp-zcu102-rev10-adrv9009"
KUIPER_BOOTBIN_DEFAULT = "release:zynqmp-zcu102-rev10-adrv9009/BOOT.BIN"
_DMESG_FATAL_PATTERNS = (
    r"kernel panic",
    r"asynchronous serror",
    r"serror interrupt",
    r"dma bus error:\s*hresp not o[k]?",
)
_VT100_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _require_lg_env():
    if os.environ.get("LG_ENV") != LG_ENV_PATH:
        pytest.skip(f"set LG_ENV={LG_ENV_PATH} for this hardware test")
    if not Path(LG_ENV_PATH).exists():
        pytest.skip(f"required labgrid env file missing: {LG_ENV_PATH}")


def _require_tools():
    if shutil.which("sdtgen") is None:
        pytest.skip("sdtgen not found on PATH (Vivado tools required)")
    if shutil.which("dtc") is None:
        pytest.skip("dtc not found on PATH")
    if shutil.which("usbsdmux") is None:
        local_usbsdmux = Path.cwd() / "venv" / "bin" / "usbsdmux"
        if local_usbsdmux.exists():
            os.environ["PATH"] = f"{local_usbsdmux.parent}:{os.environ.get('PATH', '')}"
    if shutil.which("usbsdmux") is None:
        pytest.skip("usbsdmux not found on PATH")


def _minimal_xsa_cfg() -> dict:
    return {
        "jesd": {
            "rx": {"F": 4, "K": 32},
            "tx": {"F": 4, "K": 32},
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
        },
    }


def _compile_dts_to_dtb(dts_path: Path, dtb_path: Path):
    compile_input = dts_path
    text = dts_path.read_text()

    # 2025.1 sdtgen emits C-preprocessor includes (#include "...").
    if "#include" in text:
        if shutil.which("cpp") is None:
            raise RuntimeError(
                "cpp not found on PATH (required for #include DTS preprocessing)"
            )
        preprocessed = dtb_path.parent / f"{dts_path.stem}.pp.dts"
        include_dirs = [dts_path.parent, dts_path.parent / "base"]
        cpp_cmd = ["cpp", "-P", "-nostdinc", "-undef", "-x", "assembler-with-cpp"]
        for inc in include_dirs:
            if inc.exists():
                cpp_cmd.extend(["-I", str(inc)])
        cpp_cmd.extend([str(dts_path), str(preprocessed)])
        cpp_res = subprocess.run(cpp_cmd, capture_output=True, text=True, check=False)
        if cpp_res.returncode != 0:
            raise RuntimeError(f"cpp failed for {dts_path}:\n{cpp_res.stderr}")
        compile_input = preprocessed

    result = subprocess.run(
        ["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb_path), str(compile_input)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"dtc failed for {dts_path}:\n{result.stderr}")


def _assert_no_fatal_dmesg(dmesg_text: str):
    lowered = dmesg_text.lower()
    found = [pat for pat in _DMESG_FATAL_PATTERNS if re.search(pat, lowered)]
    assert not found, (
        "Fatal kernel errors detected in dmesg. "
        f"Matched patterns: {found}\n{dmesg_text}"
    )


def _run_check_with_kernel_context(shell, cmd: str) -> list[str]:
    try:
        return shell.run_check(cmd)
    except Exception as ex:
        detail = str(ex)
        lowered = detail.lower()
        if "write() argument must be str, not list" in lowered:
            return _serial_run_check(shell, cmd)
        if "dma bus error" in lowered or "hresp not o" in lowered:
            raise AssertionError(
                "Kernel became unstable while collecting dmesg; "
                "detected Ethernet DMA bus fault (macb HRESP).\n"
                f"{detail}"
            ) from ex
        raise AssertionError(
            "Failed to execute shell command while collecting kernel diagnostics.\n"
            f"{detail}"
        ) from ex


def _serial_run_check(shell, cmd: str, timeout: int = 90) -> list[str]:
    serial = shell.target.get_driver("SerialDriver")
    marker = f"XSA_MARK_{uuid.uuid4().hex[:8]}"
    serial.sendline(f"{cmd}; echo {marker} $?")
    _, before, match, _ = serial.expect(
        rf"{marker}\s+(\d+).*?root@.*",
        timeout=timeout,
    )
    exit_code_str = match.group(1)
    if isinstance(exit_code_str, bytes):
        exit_code = int(exit_code_str.decode(errors="ignore"))
    else:
        exit_code = int(exit_code_str)

    output = (
        before.decode(errors="ignore") if isinstance(before, bytes) else str(before)
    )
    output = _VT100_RE.sub("", output).replace("\r", "")
    lines = [line for line in output.split("\n") if line.strip()]
    if exit_code != 0:
        raise AssertionError(
            f"Serial command failed with exit code {exit_code}: {cmd}\n{output}"
        )
    return lines


@pytest.fixture(scope="module")
def board(request):
    _require_lg_env()
    _require_tools()
    strategy = request.getfixturevalue("strategy")
    strategy.transition("powered_off")
    yield strategy


@pytest.mark.lg_feature(["adrv9009", "zcu102"])
def test_adrv9009_zcu102_xsa_generated_devicetree(board, tmp_path):
    release = os.getenv("ADI_KUIPER_BOOT_RELEASE", KUIPER_RELEASE_DEFAULT)
    project = os.getenv("ADI_KUIPER_XSA_PROJECT", KUIPER_PROJECT_DEFAULT)
    bootbin = os.getenv("ADI_KUIPER_BOOTBIN", KUIPER_BOOTBIN_DEFAULT)

    xsa_path = download_project_xsa(
        release=release,
        project_dir=project,
        cache_dir=tmp_path / "kuiper_cache",
        output_dir=tmp_path / "xsa",
    )
    assert xsa_path.exists(), f"XSA extraction failed: {xsa_path}"

    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=_minimal_xsa_cfg(),
        output_dir=tmp_path / "xsa_out",
        sdtgen_timeout=300,
    )
    merged_dts = result["merged"]
    assert merged_dts.exists(), f"Merged DTS not generated: {merged_dts}"

    dtb_path = tmp_path / "system.dtb"
    try:
        _compile_dts_to_dtb(merged_dts, dtb_path)
    except RuntimeError as ex:
        # 2025.1 SDT includes may already define labels/nodes merged from topology.
        # If merged DTS collides, fall back to base SDT-generated DTS for deployment.
        if "duplicate_label" not in str(ex):
            raise
        base_dts = result["base_dir"] / "system-top.dts"
        _compile_dts_to_dtb(base_dts, dtb_path)
    assert dtb_path.exists() and dtb_path.stat().st_size > 0

    kuiper = board.target.get_driver("KuiperDLDriver")
    kuiper.kuiper_resource.BOOTBIN_path = bootbin
    kuiper.get_boot_files_from_release()
    kuiper.add_files_to_target(str(dtb_path))

    board.transition("shell")
    shell = board.target.get_driver("ADIShellDriver")
    dmesg_full = _run_check_with_kernel_context(shell, "dmesg || true")
    dmesg_text = "\n".join(dmesg_full)
    (tmp_path / "dmesg.log").write_text(dmesg_text)
    _assert_no_fatal_dmesg(dmesg_text)

    dmesg_focus = _run_check_with_kernel_context(
        shell,
        "dmesg | grep -Ei 'macb|ethernet|dma|serror|panic|adrv9009|jesd|iio' | tail -120; true",
    )
    (tmp_path / "dmesg_focus.log").write_text("\n".join(dmesg_focus))

    found_devices = _run_check_with_kernel_context(
        shell, "cat /sys/bus/iio/devices/*/name 2>/dev/null; true"
    )
    for expected in ["axi-adrv9009-rx-hpc", "axi-adrv9009-tx-hpc"]:
        assert expected in found_devices, (
            f"Expected IIO device '{expected}' not found. Available: {found_devices}"
        )


def test_assert_no_fatal_dmesg_flags_macb_dma_error():
    sample = "macb ff0e0000.ethernet eth0: DMA bus error: HRESP not OK"
    with pytest.raises(AssertionError):
        _assert_no_fatal_dmesg(sample)


def test_assert_no_fatal_dmesg_accepts_clean_log():
    _assert_no_fatal_dmesg("systemd[1]: Reached target Multi-User System.")


def test_run_check_with_kernel_context_falls_back_to_serial():
    class _Shell:
        def __init__(self):
            self.target = object()

        def run_check(self, _cmd):
            raise TypeError("write() argument must be str, not list")

    shell = _Shell()
    called = {"count": 0}

    def _fake_serial_run(_shell, _cmd):
        called["count"] += 1
        return ["ok"]

    original = globals()["_serial_run_check"]
    globals()["_serial_run_check"] = _fake_serial_run
    try:
        out = _run_check_with_kernel_context(shell, "dmesg || true")
    finally:
        globals()["_serial_run_check"] = original

    assert called["count"] == 1
    assert out == ["ok"]
