"""CMOS output leg encoding.

An HMC7044 output in CMOS mode drives two independently switchable legs, P and
N. They are not a separate property: in CMOS mode the driver reuses
``adi,driver-impedance-mode`` as a two-bit output-enable field, and the bit
each leg occupies differs per channel register (see
``hmc7044_dt.cmos_outputs_reg_field_map``).

These cases cover every leg combination against every register, because the
alternating bit layout means a table edit or an encoding mistake can be
invisible for one channel and wrong for the next.
"""

import os

import fdt
import pytest

import adidt as dt

FIELD_MAP = dt.hmc7044_dt.cmos_outputs_reg_field_map
ALL_REGS = sorted(FIELD_MAP)
ALL_LEGS = [
    {"P": 0, "N": 0},
    {"P": 0, "N": 1},
    {"P": 1, "N": 0},
    {"P": 1, "N": 1},
]


def expected_value(reg, legs):
    """The value the datasheet field layout calls for."""
    return (legs["P"] << FIELD_MAP[reg]["P"]) | (legs["N"] << FIELD_MAP[reg]["N"])


def build_channel(reg, clk):
    """Run set_clock_node in isolation and hand back the node it built."""
    parent = fdt.Node("hmc7044@0")
    dt.hmc7044_dt.set_clock_node(dt.hmc7044_dt, parent, clk, f"CLKOUT{reg}", reg)
    return parent.get_subnode(f"channel@{reg}")


def cmos_clk(legs, **extra):
    return {"divider": 240, "driver-mode": "CMOS", "CMOS": legs, **extra}


@pytest.mark.parametrize("reg", ALL_REGS)
@pytest.mark.parametrize("legs", ALL_LEGS, ids=lambda v: f"P{v['P']}N{v['N']}")
def test_both_cmos_legs_are_encoded(reg, legs):
    """Both legs must reach the devicetree, for every register."""
    node = build_channel(reg, cmos_clk(legs))
    value = node.get_property("adi,driver-impedance-mode").value

    assert value == expected_value(reg, legs)


@pytest.mark.parametrize("reg", ALL_REGS)
def test_n_leg_alone_is_not_dropped(reg):
    """Enabling only N must not silently produce "both legs off".

    This is the regression that motivated the fix: the combined value was
    computed into one local and a P-only intermediate was written, so an N-only
    request encoded as 0 and the output stayed dark.
    """
    node = build_channel(reg, cmos_clk({"P": 0, "N": 1}))
    value = node.get_property("adi,driver-impedance-mode").value

    assert value != 0
    assert value == 1 << FIELD_MAP[reg]["N"]


@pytest.mark.parametrize("reg", ALL_REGS)
def test_leg_encoding_is_reversible(reg):
    """Each combination maps to a distinct value, so it can be read back."""
    seen = {expected_value(reg, legs) for legs in ALL_LEGS}
    assert len(seen) == len(ALL_LEGS)

    for legs in ALL_LEGS:
        node = build_channel(reg, cmos_clk(legs))
        value = node.get_property("adi,driver-impedance-mode").value
        decoded = {
            "P": (value >> FIELD_MAP[reg]["P"]) & 1,
            "N": (value >> FIELD_MAP[reg]["N"]) & 1,
        }
        assert decoded == legs


@pytest.mark.parametrize("reg", ALL_REGS)
def test_cmos_legs_win_over_an_explicit_impedance(reg):
    """A CMOS output may also carry an impedance; the legs take the field.

    Both settings target ``adi,driver-impedance-mode``, and appending a
    property twice raises, so supplying both used to abort node construction
    outright rather than resolve to something.
    """
    node = build_channel(
        reg, cmos_clk({"P": 1, "N": 1}, **{"driver-impedance-mode": "100_OHM"})
    )

    props = [p.name for p in node.props]
    assert props.count("adi,driver-impedance-mode") == 1
    assert node.get_property("adi,driver-impedance-mode").value == expected_value(
        reg, {"P": 1, "N": 1}
    )


@pytest.mark.parametrize("impedance", sorted(dt.hmc7044_dt.driver_impedances))
def test_non_cmos_impedance_is_untouched(impedance):
    """Outputs that are not in CMOS mode keep the impedance meaning."""
    node = build_channel(
        0,
        {
            "divider": 240,
            "driver-mode": "LVDS",
            "driver-impedance-mode": impedance,
        },
    )

    assert node.get_property("adi,driver-impedance-mode").value == (
        dt.hmc7044_dt.driver_impedances[impedance]
    )


def test_cmos_legs_survive_a_full_config_write():
    """The same encoding, driven through the public set_dt_node_from_config."""
    dtb = os.path.join(os.path.dirname(__file__), "ad9081_hmc7044.dtb")
    d = dt.hmc7044_dt(dt_source="local_file", local_dt_filepath=dtb, arch="arm64")

    config = {
        "vcxo": 125000000,
        "clock": {
            "vco": 250000000,
            "out_dividers": [3, 384],
            "output_clocks": {
                "ADC": {"divider": 3, "rate": 1e9, "driver-mode": "CML"},
                # reg 1 puts N in bit 1, so an N-only output must encode as 2.
                "SYSREF": {
                    "divider": 384,
                    "rate": 7812500.0,
                    "driver-mode": "CMOS",
                    "CMOS": {"P": 0, "N": 1},
                },
            },
        },
    }

    node = d.get_node_by_compatible("adi,hmc7044")[0]
    d.set_dt_node_from_config(node, config)

    sysref = next(
        n for n in node.nodes if n.get_property("adi,extended-name").value == "SYSREF"
    )
    reg = sysref.get_property("reg").value
    assert sysref.get_property("adi,driver-impedance-mode").value == expected_value(
        reg, {"P": 0, "N": 1}
    )
