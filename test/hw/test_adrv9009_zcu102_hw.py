"""ADRV9009 + ZCU102 hardware test driven by the XSA pipeline.

Parallels :mod:`test.hw.test_ad9081_zcu102_system_hw` stage-for-stage —
the only substantive difference is the rendering engine.  The AD9081
test composes overlays via the declarative :class:`adidt.System`; this
one uses :class:`adidt.xsa.pipeline.XsaPipeline` because
:class:`adidt.xsa.build.builders.adrv9009.ADRV9009Builder` performs extensive
topology-driven label derivation that the System path doesn't yet
cover.

After the standard boot + verify, this test sweeps four canonical
Talise filter profiles, pushing each via ``adrv9009-phy.profile_config``
and re-verifying both JESD links return to DATA.

LG_ENV: /jenkins/lg_hw.yaml.
"""

from __future__ import annotations

import base64
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from test.hw._system_base import (
    BoardSystemProfile,
    acquire_or_local_xsa,
    requires_lg,
    run_xsa_boot_and_verify,
)


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-adrv9009"
DEFAULT_VCXO_HZ = 122.88e6
DEFAULT_SAMPLE_RATE_HZ = 245.76e6


# Canonical Talise filter profiles published alongside iio-oscilloscope.
# All four share deviceClock=245.76 MHz so the JESD lane rate doesn't
# change between profiles, but the write path does re-initialise the
# radio — a useful smoke test that exercises the driver's profile-reload
# code and confirms JESD returns to DATA after each swap.
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
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / filename
    if cached.exists() and cached.stat().st_size > 0:
        return cached.read_text()
    url = f"{TALISE_PROFILE_BASE_URL}/{filename}"
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    cached.write_text(body)
    return body


def _solve_adrv9009_config(
    vcxo_hz: float = DEFAULT_VCXO_HZ,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
) -> dict[str, Any]:
    """Resolve ADRV9009 JESD framing + clock tree via pyadi-jif."""
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


def _topology_assert(topology) -> None:
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"


SPEC = BoardSystemProfile(
    lg_features=("adrv9009", "zcu102"),
    cfg_builder=_solve_adrv9009_config,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_adrv9009_zcu102.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
    ),
    topology_assert=_topology_assert,
    boot_mode="sd",
    kernel_fixture_name="built_kernel_image_zynqmp",
    out_label="adrv9009",
    dmesg_grep_pattern="adrv9009|ad9528|jesd204|probe|failed|error",
    merged_dts_must_contain=('compatible = "adi,adrv9009"',),
    probe_signature_any=("adrv9009-phy", "talise"),
    probe_signature_message="ADRV9009 phy probe signature not found in dmesg",
    iio_required_all=("adrv9009-phy", "axi-adrv9009-rx-hpc", "ad9528-1"),
    rx_capture_target_names=("axi-adrv9009-rx-hpc", "axi-adrv9009-rx-obs-hpc"),
)


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_adrv9009_zcu102_hw(board, tmp_path, request):
    """End-to-end pyadi-dt ADRV9009+ZCU102 boot + IIO verification."""
    from test.hw.hw_helpers import (
        assert_jesd_links_data,
        assert_no_kernel_faults,
        assert_no_probe_errors,
        shell_out,
    )

    shell, _ctx, _dmesg = run_xsa_boot_and_verify(
        SPEC, board=board, request=request, tmp_path=tmp_path
    )

    # --- Talise filter-profile sweep ---
    # The remote libiio write path drops its TCP socket when the driver
    # holds the CPU for Talise re-init (BrokenPipeError); push each
    # profile to /tmp via the serial shell instead, then ``cat`` it
    # into the sysfs attribute.  ``profile_config`` is exposed via
    # debugfs on ADRV9009; fall back to a broader /sys search if the
    # usual location is unavailable.
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
        dmesg = shell_out(shell, "dmesg")
        assert_no_kernel_faults(dmesg)
        assert_no_probe_errors(dmesg)
        print(f"  {filename}: RX+TX JESD DATA OK")
