"""AD9081 + ZCU102 hardware test driven by the XSA pipeline.

Parallels :mod:`test.hw.test_adrv9009_zcu102_hw` stage-for-stage, using
:class:`adidt.xsa.pipeline.XsaPipeline` + :class:`AD9081Builder` instead
of the declarative :class:`adidt.System` path.  The XSA pipeline handles
the full set of topology-driven overlays (XCVR clock refs, TPL core
binding, JESD link IDs, ``dev_clk`` phandles) that the System path does
not yet emit, so this variant reaches a fully probed IIO device where
the System test still falls short.

LG_ENV / LG_COORDINATOR: see ``.env.example``.  The test runs against
the ``mini2`` place (ZCU102 + AD9081-FMCA-EBZ) on the coordinator.
"""

from __future__ import annotations

import os
import shutil as _shutil
from pathlib import Path
from typing import Any

import pytest

if not (os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV")):
    pytest.skip(
        "set LG_COORDINATOR or LG_ENV for AD9081 ZCU102 hardware test"
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
)


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9081"
DEFAULT_VCXO_HZ = 122_880_000


def _solve_ad9081_config(vcxo_hz: int = DEFAULT_VCXO_HZ) -> dict[str, Any]:
    """Resolve AD9081 JESD mode + datapath + clocks via pyadi-jif.

    Returns the ``cfg`` dict consumed by ``XsaPipeline.run``.  Skips the
    test gracefully if ``pyadi-jif`` is not installed.
    """
    try:
        import adijif
    except ModuleNotFoundError as exc:
        pytest.skip(f"pyadi-jif not available: {exc}")

    sys = adijif.system("ad9081", "hmc7044", "xilinx", vcxo=vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")

    cddc, fddc, cduc, fduc = 4, 4, 8, 6
    sys.converter.clocking_option = "integrated_pll"
    sys.converter.adc.sample_clock = 4_000_000_000 / cddc / fddc
    sys.converter.dac.sample_clock = 12_000_000_000 / cduc / fduc
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
        pytest.skip("pyadi-jif: no matching AD9081 M8/L4 mode found")

    rx_settings = mode_rx[0]["settings"]
    tx_settings = mode_tx[0]["settings"]

    # Pin the AD9081 link modes to the jesd204b values Kuiper's stock
    # ``m8_l4_vcxo122p88/system.dtb`` uses (rx=9, tx=10).  Without this
    # override the ``(M=8, L=4)`` entry in
    # :data:`~adidt.xsa.builders.ad9081._AD9081_LINK_MODE_BY_ML` picks
    # ``(17, 18)`` which are jesd204c modes and fail ``jrx configuration
    # is not in table`` on the AD9081 driver's link-config lookup.
    return {
        "jesd": {
            "rx": {k: int(rx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
            "tx": {k: int(tx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
        },
        # Per analogdevicesinc/linux reference
        # ``zynqmp-zcu102-rev10-ad9081-m8-l4.dts``: the ``adi,tx-dacs``
        # (host TX / jrx / DAC) block uses ``link-mode = <9>`` and the
        # ``adi,rx-adcs`` (host RX / jtx / ADC) block uses
        # ``link-mode = <10>`` — the opposite of what the naming
        # might initially suggest.
        "ad9081": {
            "rx_link_mode": 10,
            "tx_link_mode": 9,
        },
    }


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_ad9081_zcu102_xsa_hw(board, built_kernel_image_zynqmp, tmp_path):
    """End-to-end pyadi-dt AD9081+ZCU102 boot + IIO verification (XSA path)."""
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Acquire the XSA for the target design ---
    xsa_path = acquire_xsa(
        Path(__file__).parent / "xsa" / "ref_data" / "system_top_ad9081_zcu102.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
        tmp_path,
    )
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    # --- 2. Parse the XSA as a sanity check on topology + fixture ---
    topology = XsaParser().parse(xsa_path)
    assert topology.has_converter_types("axi_ad9081"), (
        f"XSA topology is not AD9081: converter IPs = "
        f"{[c.ip_type for c in topology.converters]}"
    )
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"
    print(
        f"XSA topology: {len(topology.converters)} converter(s), "
        f"{len(topology.jesd204_rx)} rx jesd, {len(topology.jesd204_tx)} tx jesd"
    )

    # --- 3. Render device tree via the XSA pipeline ---
    cfg = _solve_ad9081_config()
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        profile="ad9081_zcu102",
        sdtgen_timeout=300,
    )
    merged_dts = result["merged"]
    assert merged_dts.exists(), f"Merged DTS not written: {merged_dts}"

    merged_content = merged_dts.read_text()
    assert 'compatible = "adi,ad9081"' in merged_content, (
        "AD9081 compatible string missing from merged DTS"
    )
    assert 'compatible = "adi,hmc7044"' in merged_content, (
        "HMC7044 compatible string missing from merged DTS"
    )

    # --- 4. Compile merged DTS to DTB + stage as system.dtb ---
    dtb_raw = out_dir / "ad9081_zcu102_xsa.dtb"
    compile_dts_to_dtb(merged_dts, dtb_raw)
    assert dtb_raw.exists() and dtb_raw.stat().st_size > 0, (
        f"dtc produced empty/missing DTB: {dtb_raw}"
    )

    # Kuiper's ZCU102 U-Boot loads ``system.dtb`` from the SD card; match
    # that basename so our DT actually takes effect (otherwise a stale
    # ``system.dtb`` from a previous boot would be used).
    staged_dir = out_dir / "sd_staging_xsa"
    staged_dir.mkdir(parents=True, exist_ok=True)
    dtb = staged_dir / "system.dtb"
    _shutil.copyfile(dtb_raw, dtb)

    # --- 5. Deploy + boot via labgrid ---
    shell = deploy_and_boot(board, dtb, built_kernel_image_zynqmp)

    # --- 6. Collect dmesg + key sysfs state for diagnostics ---
    dmesg_txt = collect_dmesg(
        shell,
        out_dir,
        label="ad9081_xsa",
        grep_pattern="ad9081|hmc7044|jesd204|probe|failed|error",
    )

    # --- 7. Verify: kernel probe + IIO context + JESD DATA state ---
    assert_no_kernel_faults(dmesg_txt)
    assert "AD9081 Rev." in dmesg_txt or "probed ADC AD9081" in dmesg_txt, (
        "AD9081 probe signature was not found in kernel dmesg output"
    )

    ctx, _ = open_iio_context(shell)

    found = {d.name for d in ctx.devices if d.name}
    assert "hmc7044" in found, (
        f"Expected IIO clock device 'hmc7044' not found. Devices: {sorted(found)}"
    )
    assert any(n in found for n in ("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc")), (
        f"AD9081 RX IIO frontend not found in devices: {sorted(found)}"
    )
    assert any(n in found for n in ("axi-ad9081-tx-hpc", "ad_ip_jesd204_tpl_dac")), (
        f"AD9081 TX IIO frontend not found in devices: {sorted(found)}"
    )

    # JESD link DATA state — both RX and TX must be locked.
    rx_status, tx_status = assert_jesd_links_data(
        shell,
        context="initial boot",
        rx_glob="84a90000.axi[_-]jesd204[_-]rx",
        tx_glob="84b90000.axi[_-]jesd204[_-]tx",
    )
    print(f"$ cat .../84a90000.axi?jesd204?rx/status\n{rx_status}")
    print(f"$ cat .../84b90000.axi?jesd204?tx/status\n{tx_status}")
