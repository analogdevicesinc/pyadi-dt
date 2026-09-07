from adidt.devices.transceivers import ADRV9003
from adidt.xsa.build.builders.adrv9003 import ADRV9003Builder
from adidt.xsa.parse.topology import ConverterInstance, Jesd204Instance, XsaTopology


def _topology() -> XsaTopology:
    return XsaTopology(
        fpga_part="xczu9eg_ffvb1156_-2",
        converters=[
            ConverterInstance(
                name="axi_adrv9003_0",
                ip_type="axi_adrv9003",
                base_addr=0x84A00000,
                spi_bus=0,
                spi_cs=1,
            )
        ],
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9003_rx_jesd",
                base_addr=0x84A10000,
                num_lanes=2,
                irq=None,
                link_clk="rx_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9003_tx_jesd",
                base_addr=0x84A20000,
                num_lanes=2,
                irq=None,
                link_clk="tx_clk",
                direction="tx",
            )
        ],
    )


def test_adrv9003_device_uses_navassa_binding():
    rendered = ADRV9003().render_dt(cs=1)
    assert 'compatible = "adi,adrv9003";' in rendered
    assert "adrv9002-phy@1" in rendered
    assert '"rx1_sampl_clk", "tx1_sampl_clk"' in rendered


def test_adrv9003_builder_matches_and_renders_profile_properties():
    builder = ADRV9003Builder()
    topo = _topology()
    assert builder.matches(topo, {})
    nodes = builder.build_nodes(
        None,
        topo,
        {"adrv9003_board": {"trx_profile_props": ["adi,rx-settings-rx-channels = <3>;"]}},
        "zynqmp_clk",
        71,
        "gpio",
    )
    assert len(nodes) == 1
    assert 'compatible = "adi,adrv9003";' in nodes[0]
    assert "adi,rx-settings-rx-channels = <3>;" in nodes[0]
