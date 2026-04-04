"""Unit tests for RPi board class and ADI sensor components."""

import pytest

from adidt.boards.rpi import rpi
from adidt.model import BoardModel, components
from adidt.model.renderer import BoardModelRenderer


class TestRPiBoardClass:
    def test_init_rpi5(self):
        board = rpi(platform="rpi5")
        assert board.platform == "rpi5"

    def test_init_rpi4(self):
        board = rpi(platform="rpi4")
        assert board.platform == "rpi4"

    def test_init_unsupported_platform(self):
        with pytest.raises(ValueError, match="not supported"):
            rpi(platform="rpi1")

    def test_build_model(self):
        board = rpi(platform="rpi5")
        model = board.build_model(
            components=[
                components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
            ]
        )
        assert isinstance(model, BoardModel)
        assert model.name == "rpi_rpi5"
        assert model.platform == "rpi5"
        assert len(model.components) == 1
        assert model.jesd_links == []
        assert model.fpga_config is None

    def test_build_model_multiple_devices(self):
        board = rpi(platform="rpi5")
        model = board.build_model(
            components=[
                components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
                components.adxl345(spi_bus="spi0", cs=1, interrupt_gpio=24),
                components.ad7124(spi_bus="spi1", cs=0, interrupt_gpio=22),
            ]
        )
        assert len(model.components) == 3

    def test_gen_dt_from_model(self, tmp_path):
        board = rpi(platform="rpi5")
        board.output_filename = str(tmp_path / "overlay.dts")
        model = board.build_model(
            components=[
                components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
            ]
        )
        result = board.gen_dt_from_model(model)
        assert (tmp_path / "overlay.dts").exists()
        content = (tmp_path / "overlay.dts").read_text()
        assert "/dts-v1/;" in content
        assert "/plugin/;" in content
        assert "adis16495" in content

    def test_gen_dt_requires_output_filename(self):
        board = rpi(platform="rpi5")
        model = board.build_model(components=[])
        with pytest.raises(ValueError, match="output_filename"):
            board.gen_dt_from_model(model)


class TestADXL345:
    def test_factory(self):
        comp = components.adxl345(spi_bus="spi0", cs=1, interrupt_gpio=26)
        assert comp.role == "accelerometer"
        assert comp.part == "adxl345"
        assert comp.spi_cs == 1

    def test_renders(self):
        model = BoardModel(
            name="test",
            platform="rpi5",
            components=[
                components.adxl345(spi_bus="spi0", cs=0, interrupt_gpio=26),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        out = nodes["converters"][0]
        assert 'compatible = "adi,adxl345"' in out
        assert "spi-cpol" in out
        assert "interrupts = <26" in out

    def test_no_interrupt(self):
        model = BoardModel(
            name="test",
            platform="rpi5",
            components=[components.adxl345(spi_bus="spi0", cs=0)],
        )
        nodes = BoardModelRenderer().render(model)
        assert "interrupt-parent" not in nodes["converters"][0]


class TestAD7124:
    def test_factory(self):
        comp = components.ad7124(spi_bus="spi0", cs=0, interrupt_gpio=22)
        assert comp.role == "adc"
        assert comp.part == "ad7124"

    def test_default_channels(self):
        comp = components.ad7124(spi_bus="spi0", cs=0)
        assert len(comp.config["channels"]) == 8

    def test_custom_channels(self):
        channels = [
            {"id": 0, "name": "temperature"},
            {"id": 1, "name": "pressure"},
        ]
        comp = components.ad7124(spi_bus="spi0", cs=0, channels=channels)
        assert len(comp.config["channels"]) == 2

    def test_renders(self):
        model = BoardModel(
            name="test",
            platform="rpi5",
            components=[
                components.ad7124(spi_bus="spi0", cs=0, interrupt_gpio=22),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        out = nodes["converters"][0]
        assert 'compatible = "adi,ad7124-8"' in out
        assert "channel@0" in out
        assert "channel@7" in out

    def test_renders_with_named_channels(self):
        model = BoardModel(
            name="test",
            platform="rpi5",
            components=[
                components.ad7124(
                    spi_bus="spi0",
                    cs=0,
                    channels=[{"id": 0, "name": "temp"}, {"id": 1, "name": "pres"}],
                ),
            ],
        )
        nodes = BoardModelRenderer().render(model)
        out = nodes["converters"][0]
        assert 'label = "temp"' in out
        assert 'label = "pres"' in out


class TestRPiEndToEnd:
    """End-to-end: RPi board + multiple sensors → DTS file."""

    def test_multi_sensor_overlay(self, tmp_path):
        board = rpi(platform="rpi5")
        board.output_filename = str(tmp_path / "adi-sensors.dts")

        model = board.build_model(
            components=[
                components.adis16495(
                    spi_bus="spi0", cs=0, gpio_label="gpio", interrupt_gpio=25
                ),
                components.adxl345(
                    spi_bus="spi0", cs=1, gpio_label="gpio", interrupt_gpio=24
                ),
                components.ad7124(
                    spi_bus="spi1",
                    cs=0,
                    gpio_label="gpio",
                    interrupt_gpio=22,
                    channels=[{"id": 0, "name": "ch0"}, {"id": 1, "name": "ch1"}],
                ),
            ],
            name="rpi5_sensor_suite",
        )

        assert model.name == "rpi5_sensor_suite"
        assert len(model.components) == 3

        result = board.gen_dt_from_model(model)
        content = (tmp_path / "adi-sensors.dts").read_text()

        assert "adis16495" in content
        assert "adxl345" in content
        assert "ad7124" in content
        assert "&spi0" in content
        assert "&spi1" in content
        assert content.count("{") == content.count("}")
