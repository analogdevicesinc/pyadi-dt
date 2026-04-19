"""ADRV9009 + ZCU102 hardware test driven by the XSA pipeline.

Parallels :mod:`test.hw.test_ad9081_zcu102_system_hw` stage-for-stage —
the only substantive difference is the rendering engine.  The AD9081
test composes overlays via the declarative :class:`adidt.System`; this
one uses :class:`adidt.xsa.pipeline.XsaPipeline` because
:class:`adidt.xsa.builders.adrv9009.ADRV9009Builder` performs extensive
topology-driven label derivation (xcvr, dma, clkgen, observation-link
handling) that the declarative ``System`` path doesn't yet cover.  The
same plumbing — ``XsaParser``, ``SdtgenRunner``, labgrid's
``KuiperDLDriver`` + ``ADIShellDriver`` — is exercised end-to-end.

LG_ENV: /jenkins/lg_hw.yaml
"""

from __future__ import annotations

import base64
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest

if not (os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV")):
    pytest.skip(
        "set LG_COORDINATOR or LG_ENV for ADRV9009 ZCU102 hardware test"
        " (see .env.example)",
        allow_module_level=True,
    )

from adidt.xsa.pipeline import XsaPipeline  # noqa: E402
from adidt.xsa.topology import XsaParser  # noqa: E402
from test.hw.hw_helpers import (  # noqa: E402
    DEFAULT_OUT_DIR,
    acquire_xsa,
    assert_jesd_links_data,
    assert_no_kernel_faults,
    collect_dmesg,
    compile_dts_to_dtb,
    deploy_and_boot,
    open_iio_context,
    shell_out,
)


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-adrv9009"
DEFAULT_VCXO_HZ = 122.88e6
DEFAULT_SAMPLE_RATE_HZ = 245.76e6

# Canonical Talise filter profiles published alongside iio-oscilloscope.
# Loaded post-boot via ``adrv9009-phy.profile_config``.  All four share
# deviceClock=245.76 MHz so the JESD lane rate does not change between
# profiles, but the write path does re-initialise the radio — a useful
# smoke test that exercises the driver's profile-reload code and
# confirms JESD returns to DATA after each swap.
TALISE_PROFILE_BASE_URL = (
    "https://raw.githubusercontent.com/analogdevicesinc/iio-oscilloscope/"
    "main/filters/adrv9009"
)
TALISE_PROFILE_FILES = (
    "Tx_BW100_IR122p88_Rx_BW100_OR122p88_ORx_BW100_OR122p88_DC245p76.txt",
    "Tx_BW200_IR245p76_Rx_BW100_OR122p88_ORx_BW200_OR245p76_DC245p76.txt",
    "Tx_BW200_IR245p76_Rx_BW200_OR245p76_ORx_BW200_OR245p76_DC245p76.txt",
    "Tx_BW400_IR491p52_Rx_BW100_OR122p88_ORx_BW400_OR491p52_DC245p76.txt",
)


def _fetch_talise_profile(filename: str, cache_dir: Path) -> str:
    """Fetch a Talise profile, caching into ``cache_dir``."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / filename
    if cached.exists() and cached.stat().st_size > 0:
        return cached.read_text()
    url = f"{TALISE_PROFILE_BASE_URL}/{filename}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    cached.write_text(body)
    return body


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _solve_adrv9009_config(
    vcxo_hz: float = DEFAULT_VCXO_HZ,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
) -> dict[str, Any]:
    """Resolve ADRV9009 JESD framing + clock tree via pyadi-jif.

    Skips the test gracefully if ``pyadi-jif`` is not installed.
    """
    try:
        import adijif
    except ModuleNotFoundError as exc:
        pytest.skip(f"pyadi-jif not available: {exc}")

    sys = adijif.system("adrv9009", "ad9528", "xilinx", vcxo=vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc, M=4, L=2, S=1, Np=16
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac, M=4, L=4, S=1, Np=16
    )
    if not mode_rx or not mode_tx:
        pytest.skip("pyadi-jif: no matching ADRV9009 JESD mode found")

    sys.converter.adc.set_quick_configuration_mode(
        mode_rx[0]["mode"], mode_rx[0]["jesd_class"]
    )
    sys.converter.dac.set_quick_configuration_mode(
        mode_tx[0]["mode"], mode_tx[0]["jesd_class"]
    )
    sys.converter.adc.decimation = 8
    sys.converter.adc.sample_clock = sample_rate_hz
    sys.converter.dac.interpolation = 8
    sys.converter.dac.sample_clock = sample_rate_hz

    rx_settings = mode_rx[0]["settings"]
    tx_settings = mode_tx[0]["settings"]
    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {k: int(rx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
            "tx": {k: int(tx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
        },
    }

    conf = sys.solve()
    rx_conf = conf.get("jesd_ADRV9009_RX", {})
    tx_conf = conf.get("jesd_ADRV9009_TX", {})
    for key in ("F", "K", "M", "L", "Np", "S"):
        if key in rx_conf:
            cfg["jesd"]["rx"][key] = int(rx_conf[key])
        if key in tx_conf:
            cfg["jesd"]["tx"][key] = int(tx_conf[key])
    return cfg


# ---------------------------------------------------------------------------
# Hardware test
# ---------------------------------------------------------------------------


@pytest.mark.lg_feature(["adrv9009", "zcu102"])
def test_adrv9009_zcu102_hw(board, built_kernel_image_zynqmp, tmp_path):
    """End-to-end pyadi-dt ADRV9009+ZCU102 boot + IIO verification."""
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Acquire the XSA for the target design ---
    xsa_path = acquire_xsa(
        Path(__file__).parent / "xsa" / "ref_data" / "system_top_adrv9009_zcu102.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
        tmp_path,
    )
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    # --- 2. Parse the XSA as a sanity check on topology + fixture ---
    topology = XsaParser().parse(xsa_path)
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"
    print(
        f"XSA topology: {len(topology.converters)} converter(s), "
        f"{len(topology.jesd204_rx)} rx jesd, {len(topology.jesd204_tx)} tx jesd"
    )

    # --- 3. Render device tree via the XSA pipeline ---
    cfg = _solve_adrv9009_config()
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        sdtgen_timeout=300,
    )
    merged_dts = result["merged"]
    assert merged_dts.exists(), f"Merged DTS not written: {merged_dts}"

    merged_content = merged_dts.read_text()
    assert 'compatible = "adi,adrv9009"' in merged_content, (
        "ADRV9009 compatible string missing from merged DTS"
    )

    # --- 4. Compile merged DTS to DTB ---
    dtb = out_dir / "adrv9009_zcu102.dtb"
    compile_dts_to_dtb(merged_dts, dtb)
    assert dtb.exists() and dtb.stat().st_size > 0, (
        f"dtc produced empty/missing DTB: {dtb}"
    )

    # --- 5. Deploy + boot via labgrid ---
    shell = deploy_and_boot(board, dtb, built_kernel_image_zynqmp)

    # --- 6. Collect dmesg + key sysfs state for diagnostics ---
    dmesg_txt = collect_dmesg(
        shell,
        out_dir,
        label="adrv9009",
        grep_pattern="adrv9009|ad9528|jesd204|probe|failed|error",
    )

    # --- 7. Verify: kernel probe + IIO context + JESD DATA state ---
    assert_no_kernel_faults(dmesg_txt)
    assert "adrv9009-phy" in dmesg_txt or "Talise" in dmesg_txt, (
        "ADRV9009 phy probe signature was not found in kernel dmesg output"
    )

    ctx, _ = open_iio_context(shell)

    found = [d.name for d in ctx.devices]
    expected = {
        "adrv9009-phy": "phy device",
        "axi-adrv9009-rx-hpc": "RX HPC frontend",
        "ad9528-1": "AD9528-1 clock chip",
    }
    for name, role in expected.items():
        assert name in found, (
            f"Expected IIO {role} ({name!r}) not found. Devices: {found}"
        )
        n_channels = len([c for c in ctx.devices if c.name == name][0].channels)
        print(f"  IIO {role}: {name} ({n_channels} channels)")

    # --- 8. JESD204 link DATA state via sysfs ---
    rx_status, tx_status = assert_jesd_links_data(shell, context="initial boot")
    print(f"$ cat .../axi?jesd204?rx/status\n{rx_status}")
    print(f"$ cat .../axi?jesd204?tx/status\n{tx_status}")

    # --- 9. Load all four canonical Talise filter profiles ---
    # The remote libiio write path drops its TCP socket when the driver
    # holds the CPU for Talise re-init, surfacing as ``BrokenPipeError``.
    # Push each profile file to /tmp via the serial shell instead, then
    # ``cat`` it into the sysfs attribute.
    # profile_config is exposed via debugfs on ADRV9009; fall back to a
    # broader /sys search if the usual location is unavailable.
    profile_sysfs = shell_out(
        shell,
        "find /sys/kernel/debug/iio /sys/bus/iio/devices "
        "-name profile_config 2>/dev/null | head -1",
    ).strip()
    if not profile_sysfs:
        profile_sysfs = shell_out(
            shell,
            "find /sys -name profile_config 2>/dev/null | head -1",
        ).strip()
    assert profile_sysfs, "Could not locate adrv9009-phy profile_config sysfs node"
    print(f"profile_config sysfs path: {profile_sysfs}")

    cache_dir = tmp_path / "talise_profiles"
    for filename in TALISE_PROFILE_FILES:
        body = _fetch_talise_profile(filename, cache_dir)
        assert body.lstrip().startswith("<profile "), (
            f"Profile {filename} does not look like a Talise XML profile"
        )
        print(f"Loading Talise profile: {filename} ({len(body)} bytes)")

        b64 = base64.b64encode(body.encode()).decode()
        shell_out(shell, f"printf '%s' '{b64}' | base64 -d > /tmp/talise.txt")
        size_on_target = shell_out(shell, "stat -c%s /tmp/talise.txt").strip()
        assert size_on_target == str(len(body.encode())), (
            f"Partial push of {filename}: target has {size_on_target} bytes, "
            f"expected {len(body.encode())}"
        )
        shell_out(shell, f"cat /tmp/talise.txt > {profile_sysfs}")

        # Profile reload re-runs Talise init; give the FSM a moment to
        # relock both links before re-reading sysfs status.
        time.sleep(3.0)
        assert_jesd_links_data(shell, context=f"after {filename}")
        assert_no_kernel_faults(shell_out(shell, "dmesg"))
        print(f"  {filename}: RX+TX JESD DATA OK")
