"""Unit tests for ADIS16495 IMU template and context builder."""

import pytest

from adidt.model import BoardModel, ComponentModel, components
from adidt.model.contexts import build_adis16495_ctx
from adidt.model.renderer import BoardModelRenderer


class TestAdis16495Context:
    """Test the ADIS16495 context builder."""

    def test_default_context(self):
        ctx = build_adis16495_ctx()
        assert ctx["label"] == "imu0"
        assert ctx["device"] == "adis16495"
        assert ctx["compatible"] == "adi,adis16495-1"
        assert ctx["cs"] == 0
        assert ctx["spi_max_hz"] == 2_000_000
        assert ctx["spi_cpol"] is True
        assert ctx["spi_cpha"] is True
        assert ctx["interrupt_gpio"] is None

    def test_custom_parameters(self):
        ctx = build_adis16495_ctx(
            label="imu1",
            cs=1,
            spi_max_hz=5_000_000,
            compatible="adi,adis16497-3",
            device="adis16497",
            gpio_label="gpio0",
            interrupt_gpio=17,
        )
        assert ctx["label"] == "imu1"
        assert ctx["cs"] == 1
        assert ctx["spi_max_hz"] == 5_000_000
        assert ctx["compatible"] == "adi,adis16497-3"
        assert ctx["device"] == "adis16497"
        assert ctx["gpio_label"] == "gpio0"
        assert ctx["interrupt_gpio"] == 17

    def test_no_interrupt(self):
        ctx = build_adis16495_ctx(interrupt_gpio=None)
        assert ctx["interrupt_gpio"] is None


class TestAdis16495Template:
    """Test the ADIS16495 Jinja2 template rendering."""

    def _render(self, ctx):
        model = BoardModel(
            name="test",
            platform="test",
            components=[
                ComponentModel(
                    role="imu",
                    part="adis16495",
                    template="adis16495.tmpl",
                    spi_bus="spi0",
                    spi_cs=ctx["cs"],
                    config=ctx,
                ),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        return nodes["converters"][0]

    def test_renders_compatible(self):
        ctx = build_adis16495_ctx(interrupt_gpio=25)
        out = self._render(ctx)
        assert 'compatible = "adi,adis16495-1"' in out

    def test_renders_spi_mode(self):
        ctx = build_adis16495_ctx(interrupt_gpio=25)
        out = self._render(ctx)
        assert "spi-cpol" in out
        assert "spi-cpha" in out

    def test_renders_spi_frequency(self):
        ctx = build_adis16495_ctx(spi_max_hz=3_000_000, interrupt_gpio=25)
        out = self._render(ctx)
        assert "spi-max-frequency = <3000000>" in out

    def test_renders_interrupt(self):
        ctx = build_adis16495_ctx(gpio_label="gpio", interrupt_gpio=25)
        out = self._render(ctx)
        assert "interrupt-parent = <&gpio>" in out
        assert "interrupts = <25 IRQ_TYPE_EDGE_FALLING>" in out

    def test_omits_interrupt_when_none(self):
        ctx = build_adis16495_ctx(interrupt_gpio=None)
        out = self._render(ctx)
        assert "interrupt-parent" not in out
        assert "interrupts" not in out

    def test_omits_cpol_when_false(self):
        ctx = build_adis16495_ctx(spi_cpol=False, spi_cpha=True, interrupt_gpio=25)
        out = self._render(ctx)
        assert "spi-cpol" not in out
        assert "spi-cpha" in out

    def test_renders_chip_select(self):
        ctx = build_adis16495_ctx(cs=2, interrupt_gpio=25)
        out = self._render(ctx)
        assert "adis16495@2" in out
        assert "reg = <2>" in out

    def test_renders_custom_label(self):
        ctx = build_adis16495_ctx(label="my_imu", interrupt_gpio=25)
        out = self._render(ctx)
        assert "my_imu: adis16495@0" in out

    def test_renders_variant_compatible(self):
        ctx = build_adis16495_ctx(
            compatible="adi,adis16497-3",
            device="adis16497",
            interrupt_gpio=25,
        )
        out = self._render(ctx)
        assert 'compatible = "adi,adis16497-3"' in out
        assert "adis16497@0" in out

    def test_spi_bus_wrapper(self):
        ctx = build_adis16495_ctx(interrupt_gpio=25)
        out = self._render(ctx)
        assert "&spi0 {" in out
        assert 'status = "okay"' in out


class TestAdis16495BoardModel:
    """Test BoardModel construction with ADIS16495."""

    def test_single_imu_model(self):
        model = BoardModel(
            name="rpi5_adis16495",
            platform="rpi5",
            components=[
                ComponentModel(
                    role="imu",
                    part="adis16495",
                    template="adis16495.tmpl",
                    spi_bus="spi0",
                    spi_cs=0,
                    config=build_adis16495_ctx(cs=0, interrupt_gpio=25),
                ),
            ],
        )
        assert model.name == "rpi5_adis16495"
        assert len(model.components) == 1
        assert model.get_component("imu").part == "adis16495"
        assert model.jesd_links == []
        assert model.fpga_config is None

    def test_dual_imu_model(self):
        model = BoardModel(
            name="rpi5_dual_imu",
            platform="rpi5",
            components=[
                ComponentModel(
                    role="imu",
                    part="adis16495",
                    template="adis16495.tmpl",
                    spi_bus="spi0",
                    spi_cs=0,
                    config=build_adis16495_ctx(label="imu0", cs=0, interrupt_gpio=25),
                ),
                ComponentModel(
                    role="imu",
                    part="adis16495",
                    template="adis16495.tmpl",
                    spi_bus="spi0",
                    spi_cs=1,
                    config=build_adis16495_ctx(label="imu1", cs=1, interrupt_gpio=24),
                ),
            ],
        )
        assert len(model.components) == 2
        assert len(model.get_components("imu")) == 2

        nodes = BoardModelRenderer().render(model)
        spi_block = nodes["converters"][0]
        assert "imu0: adis16495@0" in spi_block
        assert "imu1: adis16495@1" in spi_block

    def test_model_editability(self):
        model = BoardModel(
            name="test",
            platform="rpi5",
            components=[
                ComponentModel(
                    role="imu",
                    part="adis16495",
                    template="adis16495.tmpl",
                    spi_bus="spi0",
                    spi_cs=0,
                    config=build_adis16495_ctx(cs=0, interrupt_gpio=25),
                ),
            ],
        )
        # Edit GPIO pin
        model.components[0].config["interrupt_gpio"] = 17
        nodes = BoardModelRenderer().render(model)
        assert "interrupts = <17" in nodes["converters"][0]

        # Edit compatible
        model.components[0].config["compatible"] = "adi,adis16497-3"
        model.components[0].config["device"] = "adis16497"
        nodes = BoardModelRenderer().render(model)
        assert "adis16497" in nodes["converters"][0]

    def test_full_dts_output(self):
        """Verify the rendered output is valid DTS syntax."""
        model = BoardModel(
            name="rpi5_adis16495",
            platform="rpi5",
            components=[
                ComponentModel(
                    role="imu",
                    part="adis16495",
                    template="adis16495.tmpl",
                    spi_bus="spi0",
                    spi_cs=0,
                    config=build_adis16495_ctx(cs=0, interrupt_gpio=25),
                ),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        dts = "/dts-v1/;\n/plugin/;\n\n"
        for node_list in nodes.values():
            for node in node_list:
                dts += node + "\n"

        assert "/dts-v1/;" in dts
        assert "/plugin/;" in dts
        assert "&spi0 {" in dts
        assert "adis16495@0" in dts
        assert "spi-cpol;" in dts
        assert dts.count("{") == dts.count("}")


class TestComponentFactory:
    """Test the components.adis16495 factory function."""

    def test_factory_returns_component_model(self):
        comp = components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25)
        assert isinstance(comp, ComponentModel)
        assert comp.role == "imu"
        assert comp.part == "adis16495"
        assert comp.template == "adis16495.tmpl"
        assert comp.spi_bus == "spi0"
        assert comp.spi_cs == 0
        assert comp.config["interrupt_gpio"] == 25

    def test_factory_renders_correctly(self):
        model = BoardModel(
            name="test",
            platform="rpi5",
            components=[
                components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        out = nodes["converters"][0]
        assert "adis16495@0" in out
        assert "spi-cpol" in out

    def test_factory_with_variant(self):
        comp = components.adis16495(
            cs=1,
            compatible="adi,adis16497-3",
            device="adis16497",
        )
        assert comp.config["compatible"] == "adi,adis16497-3"
        assert comp.spi_cs == 1
