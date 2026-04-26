"""ADRV9009 + ZC706 hardware test.

Drives the XSA pipeline (:class:`adidt.xsa.pipeline.XsaPipeline` +
:class:`adidt.xsa.builders.adrv9009.ADRV9009Builder`) end-to-end on
real hardware attached to the ``nemo`` labgrid place.  Boot strategy
is :class:`BootFPGASoCTFTP` (Zynq-7000 TFTP boot); the DTB is renamed
to ``devicetree.dtb`` by the shared ``boot_mode="tftp"`` dispatch.

LG_ENV: lg_adrv9009_zc706_tftp.yaml.
"""

from __future__ import annotations

from typing import Any

import pytest

from test.hw._system_base import (
    BoardSystemProfile,
    acquire_or_local_xsa,
    requires_lg,
    run_xsa_boot_and_verify,
)


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv9009"


def _adrv9009_cfg() -> dict[str, Any]:
    """ADRV9009+ZC706 XSA pipeline cfg.

    Default HDL framing: RX M=4 L=2 S=1 Np=16 -> F=4; TX M=4 L=4 S=1
    Np=16 -> F=2.  Matches the pyadi-jif solver output and the Kuiper
    reference design ``zynq-zc706-adv7511-adrv9009``.

    GPIO overrides: ADRV9009Builder defaults to ZCU102 GPIOs (130/136);
    ZC706 wires the same signals to gpio0:106 (reset) and gpio0:112
    (sysref-req), matching the Kuiper production DT.
    """
    return {
        "adrv9009_board": {
            "trx_reset_gpio": 106,
            "trx_sysref_req_gpio": 112,
        },
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 4, "L": 2, "Np": 16, "S": 1},
            "tx": {"F": 2, "K": 32, "M": 4, "L": 4, "Np": 16, "S": 1},
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
        },
    }


def _topology_assert(topology) -> None:
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"


def _filter_si570_probe_noise(dmesg_txt: str) -> str:
    """Strip benign Si570 -EIO probe lines.

    The optional Si570 clock chip on the ADRV9009-FMC sometimes does
    not ACK on its default I2C address; the failure is present in the
    production reference DT too.
    """
    return "\n".join(
        line
        for line in dmesg_txt.splitlines()
        if not ("si570" in line and "failed" in line)
    )


SPEC = BoardSystemProfile(
    lg_features=("adrv9009", "zc706"),
    cfg_builder=_adrv9009_cfg,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_adrv9009_zc706.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
    ),
    sdtgen_profile="adrv9009_zc706",
    topology_assert=_topology_assert,
    boot_mode="tftp",
    kernel_fixture_name="built_kernel_image_zynq",
    out_label="adrv9009_xsa",
    dmesg_grep_pattern="adrv9009|hmc7044|ad9528|jesd204|talise|probe|failed|error",
    dmesg_filter=_filter_si570_probe_noise,
    merged_dts_must_contain=('compatible = "adi,adrv9009"',),
    probe_signature_any=("adrv9009", "talise"),
    probe_signature_message="ADRV9009 driver probe signature not found in dmesg",
    iio_required_any=("adrv9009-phy", "talise"),
    iio_frontend_label="ADRV9009 phy device",
)


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_adrv9009_zc706_xsa_hw(board, tmp_path, request):
    """End-to-end pyadi-dt ADRV9009+ZC706 via the XSA pipeline."""
    from test.hw.hw_helpers import (
        assert_ilas_aligned,
        parse_ilas_status,
        read_jesd_status,
    )

    shell, _ctx, dmesg_txt = run_xsa_boot_and_verify(
        SPEC, board=board, request=request, tmp_path=tmp_path
    )

    rx_status, tx_status = read_jesd_status(shell)
    print("=== JESD204 RX status (sysfs) ===")
    print(rx_status)
    print("=== JESD204 TX status (sysfs) ===")
    print(tx_status)

    ilas_report = parse_ilas_status(dmesg_txt)
    print("=== ADRV9009 ILAS report ===")
    print(ilas_report.summary())
    if ilas_report.fields:
        for name in ilas_report.fields:
            print(f"  mismatched: {name}")
    assert_ilas_aligned(dmesg_txt, context="adrv9009_xsa")
