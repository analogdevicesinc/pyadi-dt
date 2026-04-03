"""Unit tests for component factory functions."""

import pytest

from adidt.model import BoardModel, ComponentModel, components
from adidt.model.renderer import BoardModelRenderer


# All factories and their expected attributes
FACTORY_SPECS = [
    ("adis16495", "imu", "adis16495", "adis16495.tmpl"),
    ("hmc7044", "clock", "hmc7044", "hmc7044.tmpl"),
    ("ad9523_1", "clock", "ad9523_1", "ad9523_1.tmpl"),
    ("ad9528", "clock", "ad9528", "ad9528.tmpl"),
    ("ad9680", "adc", "ad9680", "ad9680.tmpl"),
    ("ad9144", "dac", "ad9144", "ad9144.tmpl"),
    ("ad9152", "dac", "ad9152", "ad9152.tmpl"),
    ("ad9172", "dac", "ad9172", "ad9172.tmpl"),
    ("ad9081", "transceiver", "ad9081", "ad9081_mxfe.tmpl"),
    ("ad9084", "transceiver", "ad9084", "ad9084.tmpl"),
]


class TestComponentFactories:
    """Test that all component factories return correct ComponentModel instances."""

    @pytest.mark.parametrize(
        "factory_name,expected_role,expected_part,expected_template",
        FACTORY_SPECS,
        ids=[s[0] for s in FACTORY_SPECS],
    )
    def test_factory_returns_component_model(
        self, factory_name, expected_role, expected_part, expected_template
    ):
        factory = getattr(components, factory_name)
        # Minimal kwargs — factories should have sensible defaults
        kwargs = {"spi_bus": "spi0", "cs": 0}
        # Some factories need required kwargs
        if factory_name == "hmc7044":
            kwargs.update(
                label="hmc7044",
                spi_max_hz=1000000,
                pll1_clkin_frequencies=[122880000],
                vcxo_hz=122880000,
                pll2_output_hz=3000000000,
                clock_output_names=["out0"],
                channels=[],
            )
        elif factory_name == "ad9680":
            kwargs.update(clks_str="<&clk 0>", clk_names_str='"adc_clk"')
        elif factory_name == "ad9144":
            kwargs.update(clk_ref="clk0 1")
        elif factory_name == "ad9152":
            kwargs.update(clk_ref="clk0 2")
        elif factory_name == "ad9172":
            kwargs.update(
                dac_rate_khz=12288000,
                jesd_link_mode=4,
                dac_interpolation=1,
                channel_interpolation=1,
                clock_output_divider=1,
            )
        elif factory_name == "ad9081":
            kwargs.update(
                label="mxfe0",
                gpio_label="gpio",
                reset_gpio=100,
                sysref_req_gpio=101,
                rx2_enable_gpio=102,
                rx1_enable_gpio=103,
                tx2_enable_gpio=104,
                tx1_enable_gpio=105,
                dev_clk_ref="hmc7044 2",
                rx_core_label="rx_core",
                tx_core_label="tx_core",
                rx_link_id=0,
                tx_link_id=1,
                dac_frequency_hz=12000000000,
                tx_cduc_interpolation=8,
                tx_fduc_interpolation=6,
                tx_converter_select="<&tx_fduc 0>",
                tx_lane_map="0 1 2 3 4 5 6 7",
                tx_link_mode=9,
                tx_m=8,
                tx_f=2,
                tx_k=32,
                tx_l=4,
                tx_s=1,
                adc_frequency_hz=4000000000,
                rx_cddc_decimation=4,
                rx_fddc_decimation=4,
                rx_converter_select="<&rx_fddc 0>",
                rx_lane_map="0 1 2 3 4 5 6 7",
                rx_link_mode=10,
                rx_m=8,
                rx_f=2,
                rx_k=32,
                rx_l=4,
                rx_s=1,
            )
        elif factory_name == "ad9084":
            kwargs.update(
                label="trx0_ad9084",
                gpio_label="gpio",
                reset_gpio=100,
                dev_clk_ref="hmc7044 2",
            )

        comp = factory(**kwargs)
        assert isinstance(comp, ComponentModel)
        assert comp.role == expected_role
        assert comp.part == expected_part
        assert comp.template == expected_template
        assert comp.spi_bus == "spi0"
        assert comp.spi_cs == 0
        assert isinstance(comp.config, dict)

    @pytest.mark.parametrize(
        "factory_name",
        ["adis16495", "ad9523_1", "ad9528"],
    )
    def test_factory_respects_spi_bus_and_cs(self, factory_name):
        """Test simple factories that only need spi_bus and cs."""
        factory = getattr(components, factory_name)
        comp = factory(spi_bus="spi1", cs=3)
        assert comp.spi_bus == "spi1"
        assert comp.spi_cs == 3


class TestComponentRendering:
    """Test that factory-created components render without errors."""

    def test_adis16495_renders(self):
        model = BoardModel(
            name="test",
            platform="test",
            components=[
                components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        assert nodes["converters"]
        assert "adis16495" in nodes["converters"][0]

    def test_ad9523_1_renders(self):
        model = BoardModel(
            name="test",
            platform="test",
            components=[components.ad9523_1(spi_bus="spi0", cs=0)],
        )
        nodes = BoardModelRenderer().render(model)
        assert nodes["converters"]
        assert "ad9523" in nodes["converters"][0]

    def test_multiple_components_same_bus(self):
        model = BoardModel(
            name="test",
            platform="test",
            components=[
                components.ad9523_1(spi_bus="spi0", cs=0),
                components.ad9680(
                    spi_bus="spi0",
                    cs=2,
                    clks_str="<&clk 0>",
                    clk_names_str='"adc_clk"',
                ),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        spi_block = nodes["converters"][0]
        assert "ad9523" in spi_block
        assert "ad9680" in spi_block
        assert spi_block.count("&spi0") == 1
