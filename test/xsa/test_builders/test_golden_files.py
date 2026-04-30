"""Golden-file regression tests.

These tests capture the exact DTS output for known configurations and
verify it doesn't change unintentionally.  If a builder change produces
different output, update the golden files with:

    python3 -m pytest test/xsa/test_builders/test_golden_files.py --update-golden
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adidt.model.renderer import BoardModelRenderer
from adidt.xsa.build.builders.ad9081 import AD9081Builder
from adidt.xsa.build.builders.fmcdaq2 import FMCDAQ2Builder
from adidt.xsa.parse.topology import (
    ConverterInstance,
    Jesd204Instance,
    XsaTopology,
)

HERE = Path(__file__).parent


def _render_to_str(model) -> str:
    nodes = BoardModelRenderer().render(model)
    lines = []
    for key in ("clkgens", "jesd204_rx", "jesd204_tx", "converters"):
        for node in nodes.get(key, []):
            lines.append(node)
    return "\n".join(lines) + "\n"


def _topo_fmcdaq2():
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance("axi_ad9680_jesd_rx_axi", 0x44A90000, 4, 0, "", "rx")
        ],
        jesd204_tx=[
            Jesd204Instance("axi_ad9144_jesd_tx_axi", 0x44B90000, 4, 0, "", "tx")
        ],
        clkgens=[],
        signal_connections=[],
        converters=[
            ConverterInstance("axi_ad9680", "axi_ad9680", 0x44A00000, None, None),
            ConverterInstance("axi_ad9144", "axi_ad9144", 0x44B00000, None, None),
        ],
        fpga_part="xczu9eg-ffvb1156-2-e",
    )


def _topo_ad9081():
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance("axi_mxfe_rx_jesd_rx_axi", 0x44A90000, 4, 0, "", "rx")
        ],
        jesd204_tx=[
            Jesd204Instance("axi_mxfe_tx_jesd_tx_axi", 0x44B90000, 4, 0, "", "tx")
        ],
        clkgens=[],
        signal_connections=[],
        converters=[
            ConverterInstance("axi_ad9081", "axi_ad9081", 0x44A00000, None, None)
        ],
        fpga_part="xczu9eg-ffvb1156-2-e",
    )


def _topo_ad9081_vpk180():
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance("axi_mxfe_rx_jesd_rx_axi", 0x44A90000, 8, 0, "", "rx")
        ],
        jesd204_tx=[
            Jesd204Instance("axi_mxfe_tx_jesd_tx_axi", 0x44B90000, 8, 0, "", "tx")
        ],
        clkgens=[],
        signal_connections=[],
        converters=[
            ConverterInstance("axi_ad9081", "axi_ad9081", 0x44A00000, None, None)
        ],
        fpga_part="xcvp1202-vsva2785-2MP-e-S",
    )


_AD9081_CFG = {
    "jesd": {
        "rx": {"F": 2, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1},
        "tx": {"F": 2, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1},
    },
    "ad9081": {
        "rx_link_mode": 10,
        "tx_link_mode": 9,
        "adc_frequency_hz": 4000000000,
        "dac_frequency_hz": 12000000000,
        "rx_cddc_decimation": 4,
        "rx_fddc_decimation": 4,
        "tx_cduc_interpolation": 8,
        "tx_fduc_interpolation": 6,
    },
}

_AD9081_VPK180_CFG = {
    "jesd": {
        "rx": {"F": 3, "K": 256, "M": 8, "L": 8, "Np": 12, "S": 2},
        "tx": {"F": 3, "K": 256, "M": 8, "L": 8, "Np": 12, "S": 2},
    },
    "ad9081": {
        "rx_link_mode": 26,
        "tx_link_mode": 24,
        "adc_frequency_hz": 2000000000,
        "dac_frequency_hz": 4000000000,
        "rx_cddc_decimation": 1,
        "rx_fddc_decimation": 1,
        "tx_cduc_interpolation": 2,
        "tx_fduc_interpolation": 1,
    },
}


_PS_CLK_OVERRIDES = {
    "ad9081_vpk180": ("versal_clk", 65, "gpio"),
}


@pytest.mark.parametrize(
    "name,builder_cls,topo_fn,cfg,golden_file",
    [
        ("fmcdaq2", FMCDAQ2Builder, _topo_fmcdaq2, {}, "golden_fmcdaq2.dts"),
        (
            "ad9081",
            AD9081Builder,
            _topo_ad9081,
            _AD9081_CFG,
            "golden_ad9081.dts",
        ),
        (
            "ad9081_vpk180",
            AD9081Builder,
            _topo_ad9081_vpk180,
            _AD9081_VPK180_CFG,
            "golden_ad9081_vpk180.dts",
        ),
    ],
)
def test_golden_output(name, builder_cls, topo_fn, cfg, golden_file, request):
    """Verify builder output matches the golden reference file."""
    topo = topo_fn()
    ps_clk_label, ps_clk_index, gpio_label = _PS_CLK_OVERRIDES.get(
        name, ("zynqmp_clk", 71, "gpio")
    )
    model = builder_cls().build_model(topo, cfg, ps_clk_label, ps_clk_index, gpio_label)
    actual = _render_to_str(model)

    golden_path = HERE / golden_file
    if request.config.getoption("--update-golden", default=False):
        golden_path.write_text(actual)
        pytest.skip(f"Updated {golden_file}")

    expected = golden_path.read_text()
    if actual != expected:
        # Show a useful diff
        import difflib

        diff = difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"golden/{golden_file}",
            tofile="actual",
        )
        diff_str = "".join(diff)
        pytest.fail(
            f"Output differs from golden file {golden_file}.\n"
            f"Run with --update-golden to update.\n\n{diff_str[:2000]}"
        )


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Update golden reference files instead of comparing",
    )
