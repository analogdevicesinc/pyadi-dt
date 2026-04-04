"""Shared topology fixtures for builder unit tests."""

import pytest

from adidt.xsa.topology import (
    ClkgenInstance,
    ConverterInstance,
    Jesd204Instance,
    XsaTopology,
)


@pytest.fixture
def topo_fmcdaq2():
    """FMCDAQ2 topology: AD9680 ADC + AD9144 DAC."""
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9680_jesd_rx_axi",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=0,
                link_clk="",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9144_jesd_tx_axi",
                base_addr=0x44B90000,
                num_lanes=4,
                irq=0,
                link_clk="",
                direction="tx",
            ),
        ],
        clkgens=[],
        converters=[
            ConverterInstance(
                name="axi_ad9680",
                ip_type="axi_ad9680",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_ad9144",
                ip_type="axi_ad9144",
                base_addr=0x44B00000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
        signal_connections=[],
        fpga_part="xczu9eg-ffvb1156-2-e",
    )


@pytest.fixture
def topo_fmcdaq3():
    """FMCDAQ3 topology: AD9680 ADC + AD9152 DAC."""
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9680_jesd_rx_axi",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=0,
                link_clk="",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9152_jesd_tx_axi",
                base_addr=0x44B90000,
                num_lanes=4,
                irq=0,
                link_clk="",
                direction="tx",
            ),
        ],
        clkgens=[],
        converters=[
            ConverterInstance(
                name="axi_ad9680",
                ip_type="axi_ad9680",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_ad9152",
                ip_type="axi_ad9152",
                base_addr=0x44B00000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
        signal_connections=[],
        fpga_part="xczu9eg-ffvb1156-2-e",
    )


@pytest.fixture
def topo_ad9081():
    """AD9081 MxFE topology."""
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=0,
                link_clk="",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x44B90000,
                num_lanes=4,
                irq=0,
                link_clk="",
                direction="tx",
            ),
        ],
        clkgens=[],
        converters=[
            ConverterInstance(
                name="axi_ad9081",
                ip_type="axi_ad9081",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
        signal_connections=[],
        fpga_part="xczu9eg-ffvb1156-2-e",
    )


@pytest.fixture
def topo_ad9081_vpk180():
    """AD9081 MxFE topology on Versal VPK180 (8 lanes)."""
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x44A90000,
                num_lanes=8,
                irq=0,
                link_clk="",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x44B90000,
                num_lanes=8,
                irq=0,
                link_clk="",
                direction="tx",
            ),
        ],
        clkgens=[],
        converters=[
            ConverterInstance(
                name="axi_ad9081",
                ip_type="axi_ad9081",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
        signal_connections=[],
        fpga_part="xcvp1202-vsva2785-2MP-e-S",
    )


@pytest.fixture
def topo_adrv9009():
    """ADRV9009 transceiver topology (no ORX)."""
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9009_rx_jesd_rx_axi",
                base_addr=0x44A90000,
                num_lanes=2,
                irq=0,
                link_clk="",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9009_tx_jesd_tx_axi",
                base_addr=0x44B90000,
                num_lanes=4,
                irq=0,
                link_clk="",
                direction="tx",
            ),
        ],
        clkgens=[],
        converters=[
            ConverterInstance(
                name="axi_adrv9009",
                ip_type="axi_adrv9009",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
        signal_connections=[],
        fpga_part="xczu9eg-ffvb1156-2-e",
    )
