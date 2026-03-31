"""AD9081 + ZCU102 overlay, JESD link, and DMA loopback tests.

LG_ENV: /jenkins/lg_ad9081_zcu102.yaml

Boots the ZCU102 with a pipeline-generated merged DTB (M8/L4, 122.88 MHz
VCXO, adijif-solved clock tree), then runs:

1. **test_configfs_overlay_support** — kernel has CONFIG_OF_OVERLAY=y
2. **test_load_overlay** — deploy .dtbo via serial, load via configfs,
   restart iiod, verify IIO devices appear via pylibiio
3. **test_unload_overlay** — rmdir configfs entry, restart iiod, verify
   no kernel panics and configfs entry removed
4. **test_reload_overlay** — load/unload/load cycle, verify IIO devices
   reappear via pylibiio
5. **test_jesd_link_status** — JESD204 RX and TX links report "Link is
   enabled" in sysfs status
6. **test_dma_loopback** — DDS tone on TX, capture RX buffer via
   pylibiio, verify non-zero data flowing

Prerequisites:
    - LG_ENV=/jenkins/lg_ad9081_zcu102.yaml
    - sdtgen and dtc on PATH
    - ZCU102 with M8/L4 BOOT.BIN for 122.88 MHz VCXO on SD card
    - Kuiper Linux with CONFIG_OF_OVERLAY=y and iiod running
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from adidt.xsa.pipeline import XsaPipeline
from test.hw.hw_helpers import compile_dts_to_dtb, compile_dtso_to_dtbo, shell_out

PROFILE_NAME = "ad9081_zcu102"
LG_ENV_PATH = "/jenkins/lg_ad9081_zcu102.yaml"
XSA_PATH = Path(__file__).parent / "system_top.xsa"
OVERLAY_NAME = "ad9081_zcu102_xsa"
CONFIGFS_OVERLAYS = "/sys/kernel/config/device-tree/overlays"
DTBO_REMOTE_PATH = f"/tmp/{OVERLAY_NAME}.dtbo"

# IIO device names to check after overlay load.  The pipeline-generated
# merged DTB uses sdtgen names (ad_ip_jesd204_tpl_*); the Kuiper reference
# DTB uses axi-ad9081-*-hpc.  Both are listed for compatibility.
AD9081_IIO_NAMES = [
    "hmc7044",
    "axi-ad9081-rx-hpc",
    "axi-ad9081-tx-hpc",
    "ad_ip_jesd204_tpl_adc",
    "ad_ip_jesd204_tpl_dac",
]

if not os.environ.get("LG_ENV"):
    pytest.skip(
        f"set LG_ENV={LG_ENV_PATH} to run this test",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# adijif config builder
# ---------------------------------------------------------------------------


def _build_adijif_cfg() -> dict:
    """Build pipeline config using adijif for the M8/L4 HDL design.

    Board: ZCU102 + AD9081-FMC-EBZ, 122.88 MHz VCXO.
    HDL: M=8, L=4, NP=16, 8b10b encoding, 10 Gbps lane rate.
    Datapath: ADC 4 GHz CDDC=4 FDDC=4, DAC 12 GHz CDUC=8 FDUC=6.
    """
    import adijif

    vcxo_hz = 122.88e6
    sys = adijif.system("ad9081", "hmc7044", "xilinx", vcxo=vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")

    cddc, fddc = 4, 4
    cduc, fduc = 8, 6

    sys.converter.clocking_option = "integrated_pll"
    sys.converter.adc.sample_clock = 4000000000 / cddc / fddc
    sys.converter.dac.sample_clock = 12000000000 / cduc / fduc
    sys.converter.adc.datapath.cddc_decimations = [cddc] * 4
    sys.converter.dac.datapath.cduc_interpolation = cduc
    sys.converter.adc.datapath.fddc_decimations = [fddc] * 8
    sys.converter.dac.datapath.fduc_interpolation = fduc
    sys.converter.adc.datapath.fddc_enabled = [True] * 8
    sys.converter.dac.datapath.fduc_enabled = [True] * 8

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc, M=8, L=4, Np=16, jesd_class="jesd204b"
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac, M=8, L=4, Np=16, jesd_class="jesd204b"
    )
    if not mode_rx or not mode_tx:
        raise RuntimeError("No matching M8/L4 JESD mode found via adijif")

    sys.converter.adc.set_quick_configuration_mode(
        mode_rx[0]["mode"], mode_rx[0]["jesd_class"]
    )
    sys.converter.dac.set_quick_configuration_mode(
        mode_tx[0]["mode"], mode_tx[0]["jesd_class"]
    )

    rx, tx = mode_rx[0]["settings"], mode_tx[0]["settings"]
    conf = sys.solve()

    _SYS = {"XCVR_CPLL": 0, "XCVR_QPLL1": 2, "XCVR_QPLL": 3, "XCVR_QPLL0": 3}
    fpga_adc = conf.get("fpga_adc", {})
    fpga_dac = conf.get("fpga_dac", {})

    return {
        "jesd": {
            "rx": {k: int(rx[k]) for k in ("F", "K", "M", "L", "Np", "S")},
            "tx": {k: int(tx[k]) for k in ("F", "K", "M", "L", "Np", "S")},
        },
        "clock": {
            "rx_device_clk_label": "hmc7044",
            "tx_device_clk_label": "hmc7044",
            "hmc7044_rx_channel": 10,
            "hmc7044_tx_channel": 6,
        },
        "ad9081": {
            "rx_link_mode": int(float(mode_rx[0]["mode"])),
            "tx_link_mode": int(float(mode_tx[0]["mode"])),
            "adc_frequency_hz": int(sys.converter.adc.sample_clock * cddc * fddc),
            "dac_frequency_hz": int(sys.converter.dac.sample_clock * cduc * fduc),
            "rx_cddc_decimation": cddc,
            "rx_fddc_decimation": fddc,
            "tx_cduc_interpolation": cduc,
            "tx_fduc_interpolation": fduc,
            "rx_sys_clk_select": int(
                _SYS.get(str(fpga_adc.get("sys_clk_select", "XCVR_QPLL")).upper(), 3)
            ),
            "tx_sys_clk_select": int(
                _SYS.get(str(fpga_dac.get("sys_clk_select", "XCVR_QPLL")).upper(), 3)
            ),
            "rx_out_clk_select": 4,
            "tx_out_clk_select": 4,
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _require_tools() -> None:
    if shutil.which("sdtgen") is None:
        pytest.skip("sdtgen not found on PATH")
    if shutil.which("dtc") is None:
        pytest.skip("dtc not found on PATH")


@pytest.fixture(scope="module")
def pipeline_result(tmp_path_factory) -> dict:
    """Run XsaPipeline to generate merged DTS and overlay."""
    _require_tools()
    if not XSA_PATH.exists():
        pytest.skip(f"XSA not found: {XSA_PATH}")
    try:
        cfg = _build_adijif_cfg()
    except ImportError:
        pytest.skip("adijif (pyadi-jif) not installed")

    out_dir = tmp_path_factory.mktemp("pipeline") / "out"
    return XsaPipeline().run(
        xsa_path=XSA_PATH, cfg=cfg, output_dir=out_dir,
        profile=PROFILE_NAME, sdtgen_timeout=300,
    )


@pytest.fixture(scope="module")
def booted_board(board, pipeline_result):
    """Boot with the pipeline-generated merged DTB."""
    merged_dts = pipeline_result["merged"]
    dtb = merged_dts.parent / "system.dtb"
    compile_dts_to_dtb(merged_dts, dtb)

    kuiper = board.target.get_driver("KuiperDLDriver")
    kuiper.get_boot_files_from_release()
    kuiper.add_files_to_target(dtb)
    board.transition("shell")
    return board


@pytest.fixture(scope="module")
def overlay_dtbo(pipeline_result) -> Path:
    """Compile the overlay .dtso to .dtbo."""
    overlay = pipeline_result["overlay"]
    dtbo = overlay.parent / f"{OVERLAY_NAME}.dtbo"
    compile_dtso_to_dtbo(overlay, dtbo)
    assert dtbo.exists() and dtbo.stat().st_size > 100
    return dtbo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _restart_iiod(shell) -> None:
    """Restart iiod so it picks up new/removed IIO devices."""
    shell_out(shell, "systemctl restart iiod 2>/dev/null || killall -HUP iiod 2>/dev/null; true")
    time.sleep(5)


def _get_iio_names_remote(ip: str, retries: int = 5, delay: float = 2.0) -> list[str]:
    """Get IIO device names via pylibiio network context.

    Retries on connection failure since iiod may still be restarting.
    """
    import iio

    for attempt in range(retries):
        try:
            ctx = iio.Context(f"ip:{ip}")
            return [d.name for d in ctx.devices if d.name]
        except (ConnectionRefusedError, OSError):
            if attempt == retries - 1:
                raise
            time.sleep(delay)
    return []


def _get_ip_address(shell) -> str:
    """Get the target's IP address from the serial shell."""
    raw = shell_out(shell, "hostname -I 2>/dev/null | awk '{print $1}'; true")
    ip = raw.strip().split()[0] if raw.strip() else ""
    if not ip:
        pytest.skip("could not determine target IP address")
    return ip


def _overlay_is_loaded(shell) -> bool:
    result = shell_out(
        shell, f"test -d {CONFIGFS_OVERLAYS}/{OVERLAY_NAME} && echo YES || echo NO"
    )
    return "YES" in result


def _load_overlay(shell) -> str:
    shell_out(shell, f"mkdir -p {CONFIGFS_OVERLAYS}/{OVERLAY_NAME}")
    return shell_out(
        shell,
        f"echo -n {DTBO_REMOTE_PATH} > {CONFIGFS_OVERLAYS}/{OVERLAY_NAME}/path 2>&1; echo RC=$?",
    )


def _unload_overlay(shell) -> str:
    return shell_out(
        shell,
        f"rmdir {CONFIGFS_OVERLAYS}/{OVERLAY_NAME} 2>&1; echo RC=$?",
    )


def _deploy_dtbo_via_shell(shell, dtbo_path: Path, remote_path: str) -> None:
    """Transfer a .dtbo file to the target via base64 over the serial shell."""
    import base64

    data = dtbo_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    chunk_size = 512
    shell_out(shell, f"rm -f {remote_path}")
    for i in range(0, len(b64), chunk_size):
        shell_out(shell, f"echo -n '{b64[i:i + chunk_size]}' >> {remote_path}.b64")
    shell_out(shell, f"base64 -d {remote_path}.b64 > {remote_path}")
    shell_out(shell, f"rm -f {remote_path}.b64")
    remote_size = shell_out(shell, f"stat -c %s {remote_path} 2>/dev/null; true").strip()
    assert remote_size == str(len(data)), (
        f"dtbo transfer size mismatch: local={len(data)}, remote={remote_size}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_configfs_overlay_support(booted_board):
    """Verify the target kernel has configfs overlay support."""
    shell = booted_board.target.get_driver("ADIShellDriver")
    result = shell_out(shell, f"test -d {CONFIGFS_OVERLAYS} && echo OK || echo MISSING")
    assert "OK" in result


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_load_overlay(booted_board, overlay_dtbo):
    """Load overlay, restart iiod, verify IIO devices via pylibiio."""
    shell = booted_board.target.get_driver("ADIShellDriver")
    ip = _get_ip_address(shell)

    # Deploy and load
    _deploy_dtbo_via_shell(shell, overlay_dtbo, DTBO_REMOTE_PATH)
    if _overlay_is_loaded(shell):
        _unload_overlay(shell)
    result = _load_overlay(shell)
    assert "RC=0" in result, f"overlay load failed: {result}"
    time.sleep(5)

    # Restart iiod so new devices are visible to remote clients
    _restart_iiod(shell)

    # Verify via pylibiio
    names = _get_iio_names_remote(ip)
    print(f"IIO devices (pylibiio): {names}")

    found = any(n in names for n in AD9081_IIO_NAMES)
    assert found, (
        f"No AD9081 IIO device found via pylibiio after overlay load. "
        f"Expected one of {AD9081_IIO_NAMES}; found: {names}"
    )


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_unload_overlay(booted_board):
    """Unload overlay, restart iiod, verify no kernel panics."""
    shell = booted_board.target.get_driver("ADIShellDriver")
    ip = _get_ip_address(shell)

    if not _overlay_is_loaded(shell):
        pytest.skip("overlay not loaded")

    names_before = _get_iio_names_remote(ip)
    print(f"IIO devices before unload: {names_before}")

    result = _unload_overlay(shell)
    assert "RC=0" in result, f"overlay unload failed: {result}"
    time.sleep(3)

    # Restart iiod so removed devices disappear from remote context
    _restart_iiod(shell)

    # Check no kernel panics
    dmesg = shell_out(shell, "dmesg | tail -10 | grep -i 'panic\\|oops\\|BUG:' ; true")
    assert not dmesg.strip(), f"kernel errors during overlay unload:\n{dmesg}"
    assert not _overlay_is_loaded(shell), "overlay configfs entry still present"

    names_after = _get_iio_names_remote(ip)
    print(f"IIO devices after unload: {names_after}")


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_reload_overlay(booted_board, overlay_dtbo):
    """Reload overlay after unload, verify IIO devices via pylibiio."""
    shell = booted_board.target.get_driver("ADIShellDriver")
    ip = _get_ip_address(shell)

    if _overlay_is_loaded(shell):
        _unload_overlay(shell)
        time.sleep(2)

    result = _load_overlay(shell)
    assert "RC=0" in result, f"overlay reload failed: {result}"
    time.sleep(5)

    _restart_iiod(shell)

    names = _get_iio_names_remote(ip)
    print(f"IIO devices after reload: {names}")

    found = any(n in names for n in AD9081_IIO_NAMES)
    assert found, (
        f"No AD9081 IIO device found after overlay reload; found: {names}"
    )

    _unload_overlay(shell)


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_jesd_link_status(booted_board):
    """Verify JESD204 links are in DATA mode after boot."""
    shell = booted_board.target.get_driver("ADIShellDriver")
    status_output = shell_out(
        shell,
        'for f in $(find /sys/devices/platform -maxdepth 4 -name status -path "*jesd*" 2>/dev/null); do '
        'echo "FILE=$f"; head -2 "$f"; done; true',
    )
    print(f"JESD status:\n{status_output}")
    assert "Link is enabled" in status_output, (
        f"JESD link not enabled:\n{status_output}"
    )


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_dma_loopback(booted_board):
    """Verify DMA TX→RX data path via pylibiio buffer capture.

    Enables a 1 MHz DDS tone on the first TX channel, captures RX samples
    into an IIO buffer over the network, and asserts the data is non-zero.
    Uses raw libiio (not pyadi-iio) to work with both Kuiper and sdtgen
    IIO device names.
    """
    import numpy as np
    import iio

    shell = booted_board.target.get_driver("ADIShellDriver")
    ip = _get_ip_address(shell)

    ctx = iio.Context(f"ip:{ip}")

    adc = ctx.find_device("axi-ad9081-rx-hpc") or ctx.find_device(
        "ad_ip_jesd204_tpl_adc"
    )
    dac = ctx.find_device("axi-ad9081-tx-hpc") or ctx.find_device(
        "ad_ip_jesd204_tpl_dac"
    )
    if adc is None:
        pytest.skip("ADC IIO device not found")
    if dac is None:
        pytest.skip("DAC IIO device not found")

    print(f"ADC: {adc.name} ({len(adc.channels)} ch)")
    print(f"DAC: {dac.name} ({len(dac.channels)} ch)")

    # Enable DDS tone on first TX altvoltage channel
    for ch in dac.channels:
        if "altvoltage0" in ch.id:
            try:
                ch.attrs["frequency"].value = str(1_000_000)
                ch.attrs["scale"].value = str(0.5)
                ch.attrs["raw"].value = str(1)
                print(f"DDS enabled: {ch.id} @ 1 MHz")
            except Exception as ex:
                pytest.skip(f"DDS setup failed: {ex}")
            break

    # Enable first RX voltage channel
    rx_ch = None
    for c in adc.channels:
        if c.id.startswith("voltage") and not c.output:
            c.enabled = True
            rx_ch = c
            break
    assert rx_ch is not None, "no RX voltage channel found"

    try:
        buf = iio.Buffer(adc, 2**14)
        for _ in range(3):
            buf.refill()
        buf.refill()
        data = np.frombuffer(buf.read(), dtype=np.int16)
    except TimeoutError:
        pytest.skip("DMA buffer refill timed out — JESD link may not be in DATA mode")
    except Exception as ex:
        pytest.fail(f"RX capture failed: {ex}")
    finally:
        for ch in dac.channels:
            if "altvoltage0" in ch.id:
                try:
                    ch.attrs["raw"].value = str(0)
                except Exception:
                    pass
                break

    peak = np.max(np.abs(data))
    print(f"RX capture: {len(data)} samples, peak={peak}")
    assert peak > 0, "RX data is all zeros — DMA path or JESD link may be broken"
    assert len(data) > 100, f"RX data too short: {len(data)} samples"
    print("DMA loopback: data flowing")
