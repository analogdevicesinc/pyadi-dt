"""Tests for the component class hierarchy and backward compatibility."""

from __future__ import annotations

import pytest

from adidt.model.board_model import ComponentModel
from adidt.model.components import (
    AdcComponent,
    ClockComponent,
    DacComponent,
    JesdDeviceMixin,
    JESD_PARAM_NAMES,
    JESD_SUBCLASS_MAP,
    RfFrontendComponent,
    SensorComponent,
    TransceiverComponent,
)
from adidt.model.components.base import JesdDeviceMixin as BaseMixin


# ---------------------------------------------------------------------------
# Base class inheritance
# ---------------------------------------------------------------------------


class TestInheritance:
    """Verify subclass relationships."""

    def test_clock_is_component(self):
        assert issubclass(ClockComponent, ComponentModel)

    def test_adc_is_component(self):
        assert issubclass(AdcComponent, ComponentModel)

    def test_dac_is_component(self):
        assert issubclass(DacComponent, ComponentModel)

    def test_transceiver_is_component(self):
        assert issubclass(TransceiverComponent, ComponentModel)

    def test_sensor_is_component(self):
        assert issubclass(SensorComponent, ComponentModel)

    def test_rf_frontend_is_component(self):
        assert issubclass(RfFrontendComponent, ComponentModel)

    def test_adc_has_jesd_mixin(self):
        assert issubclass(AdcComponent, JesdDeviceMixin)

    def test_dac_has_jesd_mixin(self):
        assert issubclass(DacComponent, JesdDeviceMixin)

    def test_transceiver_has_jesd_mixin(self):
        assert issubclass(TransceiverComponent, JesdDeviceMixin)

    def test_clock_no_jesd_mixin(self):
        assert not issubclass(ClockComponent, JesdDeviceMixin)

    def test_sensor_no_jesd_mixin(self):
        assert not issubclass(SensorComponent, JesdDeviceMixin)


# ---------------------------------------------------------------------------
# Role defaults
# ---------------------------------------------------------------------------


ROLE_SPECS = [
    (ClockComponent, "from_config", {"part": "x", "template": "x.tmpl"}, "clock"),
    (AdcComponent, "from_config", {"part": "x", "template": "x.tmpl"}, "adc"),
    (DacComponent, "from_config", {"part": "x", "template": "x.tmpl"}, "dac"),
    (
        TransceiverComponent,
        "from_config",
        {"part": "x", "template": "x.tmpl"},
        "transceiver",
    ),
    (
        SensorComponent,
        "from_config",
        {"part": "x", "template": "x.tmpl", "role": "imu"},
        "imu",
    ),
    (
        SensorComponent,
        "from_config",
        {"part": "x", "template": "x.tmpl", "role": "accelerometer"},
        "accelerometer",
    ),
    (
        RfFrontendComponent,
        "from_config",
        {"part": "x", "template": "x.tmpl"},
        "rf_frontend",
    ),
]


class TestRoleDefaults:
    """Verify that from_config sets the expected role."""

    @pytest.mark.parametrize(
        "cls,method,kwargs,expected_role",
        ROLE_SPECS,
        ids=[f"{s[0].__name__}-{s[3]}" for s in ROLE_SPECS],
    )
    def test_from_config_role(self, cls, method, kwargs, expected_role):
        comp = getattr(cls, method)(**kwargs)
        assert comp.role == expected_role
        assert isinstance(comp, ComponentModel)


# ---------------------------------------------------------------------------
# Factory output
# ---------------------------------------------------------------------------


class TestFactoryOutput:
    """Verify that device-specific factories populate fields correctly."""

    def test_ad9523_1_factory(self):
        comp = ClockComponent.ad9523_1(spi_bus="spi1", cs=2)
        assert comp.part == "ad9523_1"
        assert comp.template == "ad9523_1.tmpl"
        assert comp.spi_bus == "spi1"
        assert comp.spi_cs == 2
        assert isinstance(comp.config, dict)
        assert isinstance(comp, ClockComponent)

    def test_ad9528_factory(self):
        comp = ClockComponent.ad9528()
        assert comp.part == "ad9528"
        assert comp.role == "clock"

    def test_ad9680_factory(self):
        comp = AdcComponent.ad9680(
            spi_bus="spi0",
            cs=1,
            clks_str="<&clk 0>",
            clk_names_str='"adc_clk"',
        )
        assert comp.part == "ad9680"
        assert comp.role == "adc"
        assert isinstance(comp, AdcComponent)

    def test_ad9144_factory(self):
        comp = DacComponent.ad9144(cs=3, clk_ref="clk0 1")
        assert comp.part == "ad9144"
        assert comp.spi_cs == 3

    def test_adis16495_factory(self):
        comp = SensorComponent.adis16495(interrupt_gpio=25)
        assert comp.part == "adis16495"
        assert comp.role == "imu"
        assert isinstance(comp, SensorComponent)

    def test_adxl345_factory(self):
        comp = SensorComponent.adxl345()
        assert comp.part == "adxl345"
        assert comp.role == "accelerometer"


# ---------------------------------------------------------------------------
# from_config generic factory
# ---------------------------------------------------------------------------


class TestFromConfig:
    """Verify from_config creates valid instances."""

    def test_clock_from_config(self):
        comp = ClockComponent.from_config(
            part="ltc6953", template="ltc6953.tmpl", config={"foo": 1}
        )
        assert comp.part == "ltc6953"
        assert comp.config == {"foo": 1}
        assert isinstance(comp, ClockComponent)

    def test_from_config_default_config(self):
        comp = AdcComponent.from_config(part="x", template="x.tmpl")
        assert comp.config == {}

    def test_rf_frontend_from_config(self):
        comp = RfFrontendComponent.from_config(part="hmc123", template="hmc123.tmpl")
        assert comp.role == "rf_frontend"
        assert isinstance(comp, RfFrontendComponent)


# ---------------------------------------------------------------------------
# JesdDeviceMixin
# ---------------------------------------------------------------------------


class TestJesdDeviceMixin:
    """Test JESD parameter validation and subclass mapping."""

    def test_validate_valid_params(self):
        JesdDeviceMixin.validate_jesd_params({"F": 2, "K": 32, "M": 4})

    def test_validate_invalid_zero(self):
        with pytest.raises(ValueError, match="positive integer"):
            JesdDeviceMixin.validate_jesd_params({"F": 0})

    def test_validate_invalid_negative(self):
        with pytest.raises(ValueError, match="positive integer"):
            JesdDeviceMixin.validate_jesd_params({"L": -1})

    def test_validate_invalid_type(self):
        with pytest.raises(ValueError, match="positive integer"):
            JesdDeviceMixin.validate_jesd_params({"M": "4"})

    def test_validate_with_direction(self):
        with pytest.raises(ValueError, match="rx JESD parameter"):
            JesdDeviceMixin.validate_jesd_params({"F": 0}, direction="rx")

    def test_validate_ignores_unknown_keys(self):
        # Keys not in JESD_PARAM_NAMES are silently ignored
        JesdDeviceMixin.validate_jesd_params({"foo": "bar", "F": 1})

    def test_map_subclass_a(self):
        assert JesdDeviceMixin.map_jesd_subclass("jesd204a") == 0

    def test_map_subclass_b(self):
        assert JesdDeviceMixin.map_jesd_subclass("jesd204b") == 1

    def test_map_subclass_c(self):
        assert JesdDeviceMixin.map_jesd_subclass("jesd204c") == 2

    def test_map_subclass_unknown(self):
        with pytest.raises(ValueError, match="Unknown JESD subclass"):
            JesdDeviceMixin.map_jesd_subclass("jesd204d")

    def test_param_names_tuple(self):
        assert JESD_PARAM_NAMES == ("F", "K", "M", "L", "Np", "S")

    def test_subclass_map_dict(self):
        assert JESD_SUBCLASS_MAP == {"jesd204a": 0, "jesd204b": 1, "jesd204c": 2}

    def test_mixin_reexport(self):
        """JesdDeviceMixin from __init__ is the same class as from base."""
        assert JesdDeviceMixin is BaseMixin


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Verify standalone function aliases work as before."""

    def test_import_standalone_functions(self):
        from adidt.model.components import (
            ad7124,
            ad9081,
            ad9084,
            ad9144,
            ad9152,
            ad9172,
            ad9523_1,
            ad9528,
            ad9680,
            adis16495,
            adxl345,
            hmc7044,
        )

        # All should be callable
        assert callable(hmc7044)
        assert callable(ad9523_1)
        assert callable(ad9528)
        assert callable(ad9680)
        assert callable(ad9144)
        assert callable(ad9152)
        assert callable(ad9172)
        assert callable(ad9081)
        assert callable(ad9084)
        assert callable(adis16495)
        assert callable(adxl345)
        assert callable(ad7124)

    def test_module_import_pattern(self):
        """from adidt.model import components; components.hmc7044() works."""
        from adidt.model import components

        comp = components.ad9523_1(spi_bus="spi0", cs=0)
        assert comp.part == "ad9523_1"
        assert isinstance(comp, ComponentModel)

    def test_standalone_returns_component_model(self):
        from adidt.model.components import adis16495

        comp = adis16495(spi_bus="spi0", cs=0)
        assert isinstance(comp, ComponentModel)
        assert comp.role == "imu"

    def test_standalone_returns_typed_subclass(self):
        from adidt.model.components import ad9680

        comp = ad9680(spi_bus="spi0", cs=0, clks_str="<&clk 0>", clk_names_str='"adc_clk"')
        assert isinstance(comp, AdcComponent)
        assert isinstance(comp, ComponentModel)


# ---------------------------------------------------------------------------
# New factory tests (Task 3+4)
# ---------------------------------------------------------------------------

# Each tuple: (class, factory_method_name, extra_kwargs, expected_part, expected_role)
NEW_FACTORY_SPECS = [
    # Clocks
    (ClockComponent, "ad9545", {}, "ad9545", "clock"),
    (ClockComponent, "ltc6952", {}, "ltc6952", "clock"),
    (ClockComponent, "ltc6953", {}, "ltc6953", "clock"),
    (ClockComponent, "adf4371", {}, "adf4371", "clock"),
    (ClockComponent, "adf4377", {}, "adf4377", "clock"),
    (ClockComponent, "adf4350", {}, "adf4350", "clock"),
    (ClockComponent, "adf4030", {}, "adf4030", "clock"),
    # ADCs
    (AdcComponent, "ad9088", {}, "ad9088", "adc"),
    (AdcComponent, "ad9467", {}, "ad9467", "adc"),
    (AdcComponent, "ad7768", {}, "ad7768", "adc"),
    (AdcComponent, "adaq8092", {}, "adaq8092", "adc"),
    # DACs
    (DacComponent, "ad9739a", {}, "ad9739a", "dac"),
    (DacComponent, "ad916x", {}, "ad916x", "dac"),
    # Transceivers — ad9083 needs no extra args
    (TransceiverComponent, "ad9083", {}, "ad9083", "transceiver"),
    # RF front-ends
    (RfFrontendComponent, "admv1013", {}, "admv1013", "rf_frontend"),
    (RfFrontendComponent, "admv1014", {}, "admv1014", "rf_frontend"),
    (RfFrontendComponent, "adrf6780", {}, "adrf6780", "rf_frontend"),
    (RfFrontendComponent, "adar1000", {}, "adar1000", "rf_frontend"),
]


class TestNewFactories:
    """Parametrized test for all new device-specific factories."""

    @pytest.mark.parametrize(
        "cls,method,kwargs,expected_part,expected_role",
        NEW_FACTORY_SPECS,
        ids=[f"{s[0].__name__}.{s[1]}" for s in NEW_FACTORY_SPECS],
    )
    def test_factory_basics(self, cls, method, kwargs, expected_part, expected_role):
        comp = getattr(cls, method)(**kwargs)
        assert comp.part == expected_part
        assert comp.role == expected_role
        assert isinstance(comp, cls)
        assert isinstance(comp, ComponentModel)
        assert isinstance(comp.config, dict)
        assert comp.template.endswith(".tmpl")

    def test_ad9082_factory(self):
        """AD9082 requires the same kwargs as AD9081 (delegates)."""
        comp = TransceiverComponent.ad9082(
            cs=1,
            label="mxfe0",
            gpio_label="gpio0",
            sysref_req_gpio=5,
            rx2_enable_gpio=6,
            rx1_enable_gpio=7,
            tx2_enable_gpio=8,
            tx1_enable_gpio=9,
            dev_clk_ref="clk 0",
            rx_core_label="rx_tpl",
            tx_core_label="tx_tpl",
            rx_link_id=0,
            tx_link_id=1,
            dac_frequency_hz=12_000_000_000,
            tx_cduc_interpolation=12,
            tx_fduc_interpolation=4,
            tx_converter_select="0xAB",
            tx_lane_map="0x01234567",
            tx_link_mode=9,
            tx_m=8,
            tx_f=2,
            tx_k=32,
            tx_l=4,
            tx_s=1,
            adc_frequency_hz=4_000_000_000,
            rx_cddc_decimation=4,
            rx_fddc_decimation=4,
            rx_converter_select="0xFF",
            rx_lane_map="0x76543210",
            rx_link_mode=10,
            rx_m=8,
            rx_f=2,
            rx_k=32,
            rx_l=4,
            rx_s=1,
        )
        assert comp.part == "ad9082"
        assert comp.role == "transceiver"
        assert isinstance(comp, TransceiverComponent)

    def test_ad9083_factory_custom(self):
        comp = TransceiverComponent.ad9083(cs=2, adc_frequency_hz=2_000_000_000)
        assert comp.spi_cs == 2
        assert comp.config["adc_frequency_hz"] == 2_000_000_000
