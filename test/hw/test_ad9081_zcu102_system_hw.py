"""AD9081 + ZCU102 hardware test driven by the declarative ``adidt.System`` API.

Exercises every stage of pyadi-dt end-to-end:

1. **XSA parsing** — :class:`adidt.xsa.parse.topology.XsaParser` extracts the
   FPGA IP topology from the Vivado archive.
2. **Base DTS generation** — :class:`adidt.xsa.parse.sdtgen.SdtgenRunner`
   produces the platform ``system-top.dts`` for ZCU102.
3. **Declarative device composition** — :class:`adidt.eval.ad9081_fmc`
   + :class:`adidt.fpga.zcu102` are wired with SPI / JESD-link
   connections through :class:`adidt.System`; ``System.generate_dts``
   emits the MxFE + HMC7044 + ADXCVR / JESD204 / TPL-core overlays.
4. **DTS merge** — :class:`adidt.xsa.merge.merger.DtsMerger` splices the
   overlay into the base DTS.
5. **Standard boot + verify** — delegated to
   :func:`test.hw._system_base.boot_and_verify_from_merged_dts`
   (compile DTS → stage as ``system.dtb`` → labgrid boot → dmesg →
   IIO probe → JESD DATA → RX capture).

LG_ENV: /jenkins/lg_ad9081_zcu102.yaml.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import adidt
from adidt.xsa.merge.merger import DtsMerger
from adidt.xsa.parse.sdtgen import SdtgenRunner
from adidt.xsa.parse.topology import XsaParser
from test.hw._system_base import (
    BoardSystemProfile,
    acquire_or_local_xsa,
    boot_and_verify_from_merged_dts,
    requires_lg,
)
from test.hw.hw_helpers import DEFAULT_OUT_DIR


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9081"
DEFAULT_VCXO_HZ = 122_880_000


def _solve_ad9081_config(vcxo_hz: int = DEFAULT_VCXO_HZ) -> dict:
    """Resolve AD9081 JESD mode + datapath + clocks via pyadi-jif."""
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

    return {
        "rx_sample_rate": int(sys.converter.adc.sample_clock),
        "tx_sample_rate": int(sys.converter.dac.sample_clock),
        "rx_cddc": cddc,
        "rx_fddc": fddc,
        "tx_cduc": cduc,
        "tx_fduc": fduc,
        # pyadi-jif reports mode numbers as stringified floats ("10.0"), so
        # round-trip through ``float`` before casting to int.
        "rx_mode": int(float(mode_rx[0]["mode"])),
        "tx_mode": int(float(mode_tx[0]["mode"])),
        "rx_class": mode_rx[0]["jesd_class"],
        "tx_class": mode_tx[0]["jesd_class"],
    }


def _configure_converter(fmc, cfg: dict) -> None:
    """Apply solver-resolved JESD + datapath values to the AD9081 device.

    AD9081 uses *different* jesd204b link modes for the ADC (RX, jtx)
    and DAC (TX, jrx) — see the per-side ``MODE_TABLE`` in
    :mod:`adidt.devices.converters.ad9081`.  Applying the same mode to
    both sides via ``converter.set_jesd204_mode`` leaves the DAC
    mode-table lookup empty and L=0, which makes the kernel driver
    fail at ``adi_ad9081_device_startup_tx_or_nco_test``.
    """
    fmc.converter.adc.set_jesd204_mode(cfg["rx_mode"], cfg["rx_class"])
    fmc.converter.dac.set_jesd204_mode(cfg["tx_mode"], cfg["tx_class"])
    fmc.converter.adc.sample_rate = cfg["rx_sample_rate"]
    fmc.converter.dac.sample_rate = cfg["tx_sample_rate"]
    fmc.converter.adc.cddc_decimation = cfg["rx_cddc"]
    fmc.converter.adc.fddc_decimation = cfg["rx_fddc"]
    fmc.converter.dac.cduc_interpolation = cfg["tx_cduc"]
    fmc.converter.dac.fduc_interpolation = cfg["tx_fduc"]


# Reuse the AD9081+ZCU102 SPEC for the post-render boot+verify steps.
# `cfg_builder` and `xsa_resolver` are unused here (the System API path
# does its own composition + sdtgen rather than running XsaPipeline) but
# the rest of the SPEC — boot mode, IIO requirements, JESD globs, RX
# capture targets — is identical to the XSA-pipeline AD9081 test.
SPEC = BoardSystemProfile(
    lg_features=("ad9081", "zcu102"),
    cfg_builder=_solve_ad9081_config,
    xsa_resolver=acquire_or_local_xsa(
        "system_top.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
    ),
    boot_mode="sd",
    kernel_fixture_name="built_kernel_image_zynqmp",
    out_label="ad9081_system",
    dmesg_grep_pattern="ad9081|hmc7044|jesd204|probe|failed|error",
    probe_signature_any=("AD9081 Rev.", "probed ADC AD9081"),
    probe_signature_message="AD9081 probe signature not found in dmesg",
    iio_required_all=("hmc7044",),
    iio_required_any_groups=(
        ("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc"),
        ("axi-ad9081-tx-hpc", "ad_ip_jesd204_tpl_dac"),
    ),
    jesd_rx_glob="84a90000.axi[_-]jesd204[_-]rx",
    jesd_tx_glob="84b90000.axi[_-]jesd204[_-]tx",
    rx_capture_target_names=("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc"),
)


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_ad9081_zcu102_system_hw(board, tmp_path, request):
    """Compose an AD9081+ZCU102 design via the System API and boot it."""
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Acquire the XSA for the target design ---
    xsa_path = SPEC.xsa_resolver(tmp_path)
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    # --- 2. Parse the XSA + sanity-check topology ---
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

    # --- 3. Run sdtgen for the platform base DTS ---
    base_dir = out_dir / "base"
    base_dir.mkdir(exist_ok=True)
    base_dts_path = SdtgenRunner().run(xsa_path, base_dir, timeout=300)
    base_dts = base_dts_path.read_text()

    # --- 4. Compose the design declaratively via adidt.System ---
    cfg = SPEC.cfg_builder()

    fmc = adidt.eval.ad9081_fmc(reference_frequency=DEFAULT_VCXO_HZ)
    _configure_converter(fmc, cfg)

    fpga = adidt.fpga.zcu102()
    system = adidt.System(name="ad9081_zcu102_system", components=[fmc, fpga])

    # Pull real AXI JESD204 RX/TX IP instance names out of the XSA so
    # the emitted ``&<label> { ... };`` overlays target nodes that
    # actually exist in the sdtgen base DTS (production ZCU102 AD9081
    # projects use ``axi_jesd204_rx_0`` / ``axi_jesd204_tx_0`` rather
    # than the hardcoded ``axi_mxfe_*_jesd_*_axi`` convention).
    system.apply_xsa_topology(topology)

    # Wire the two SPI buses.  On the AD9081-FMCA-EBZ + ZCU102, the
    # AD9081 sits on spi0 (ff040000) and the HMC7044 on spi1 (ff050000)
    # — swapping these causes the HMC7044 to fail its initial SPI
    # read/write check at probe time.
    system.connect_spi(
        bus_index=0, primary=fpga.spi[0], secondary=fmc.converter.spi, cs=0
    )
    system.connect_spi(bus_index=1, primary=fpga.spi[1], secondary=fmc.clock.spi, cs=0)

    # ADC → FPGA (RX).
    system.add_link(
        source=fmc.converter.adc,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.dev_refclk,
        sink_core_clock=fmc.core_clk_rx,
        sink_sysref=fmc.dev_sysref,
    )
    # FPGA → DAC (TX).
    system.add_link(
        source=fpga.gt[1],
        sink=fmc.converter.dac,
        source_reference_clock=fmc.fpga_refclk_tx,
        source_core_clock=fmc.core_clk_tx,
        sink_sysref=fmc.fpga_sysref,
    )

    # --- 5. Render the overlay DTS and merge into the XSA base ---
    model = system.to_board_model()
    assert model.get_component("clock").part == "hmc7044"
    assert model.get_component("converter").part == "ad9081"
    assert {link.direction for link in model.jesd_links} == {"rx", "tx"}

    nodes = adidt.BoardModelRenderer().render(model)
    assert nodes["converters"], "BoardModelRenderer emitted no converter nodes"

    merged_name = "ad9081_zcu102_system"
    _, merged_content = DtsMerger().merge(base_dts, nodes, out_dir, merged_name)
    assert 'compatible = "adi,hmc7044";' in merged_content, (
        "HMC7044 node missing from merged DTS"
    )
    assert 'compatible = "adi,ad9081";' in merged_content, (
        "AD9081 node missing from merged DTS"
    )

    # --- 6-9. Compile + stage + boot + verify via the shared helper ---
    merged_dts = out_dir / f"{merged_name}.dts"
    boot_and_verify_from_merged_dts(
        SPEC,
        merged_dts,
        board=board,
        request=request,
        out_dir=out_dir,
        dtb_basename=f"{merged_name}.dtb",
    )
