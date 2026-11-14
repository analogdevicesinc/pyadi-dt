"""Declarative design profiles: DTS source parsing, seeding and rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adidt.xsa.build.builders.declarative import DESIGN_KEY, DeclarativeBuilder
from adidt.xsa.build.node_builder import NodeBuilder
from adidt.xsa.config.profiles import ProfileManager
from adidt.xsa.declarative.dts_source import DtsSyntaxError, DtsTree, parse_cells
from adidt.xsa.declarative.seed import seed_design
from adidt.xsa.exceptions import ProfileError
from adidt.xsa.merge.merger import DtsMerger
from adidt.xsa.parse.topology import AxiIpInstance, XsaParser, XsaTopology
from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.validate.bindings import adi_bindings, missing_bindings

# A reference tree as cpp emits it: line markers attribute each part to the
# carrier file ("board.dts") or the design file ("design.dts").
REFERENCE = """
# 1 "board.dts"
/dts-v1/;
/ {
	model = "carrier";
	amba: axi {
		compatible = "simple-bus";
		spi0: spi@ff040000 {
			compatible = "cdns,spi-r1p6";
			status = "disabled";
		};
		i2c1: i2c@ff030000 {
			compatible = "cdns,i2c-r1p14";
			mux: i2c-mux@74 {
				compatible = "nxp,pca9548";
				reg = <0x74>;
				i2c@0 {
					reg = <0>;
					si570: clock-generator@5d {
						compatible = "silabs,si570";
						reg = <0x5d>;
					};
				};
			};
		};
	};
	board_only: board-regulator {
		compatible = "regulator-fixed";
	};
};
# 1 "design.dts"
/ {
	clocks {
		ref_clk: clock@0 {
			compatible = "fixed-clock";
			#clock-cells = <0>;
		};
	};
	fpga_axi: fpga-axi@0 {
		compatible = "simple-bus";
		#address-cells = <0x1>;
		#size-cells = <0x1>;
		rx_dma: dma-controller@9c400000 {
			compatible = "adi,axi-dmac-1.00.a";
			reg = <0x9c400000 0x10000>;
			interrupts = <0 109 4>;
			clocks = <&zynqmp_clk 73>;
		};
		axi_core: axi-adc@84a00000 {
			compatible = "adi,axi-adc-10.0.a";
			reg = <0x84a00000 0x8000>;
			interrupts = <0 107 4>;
			dmas = <&rx_dma 0>;
			spibus-connected = <&adc0>;
		};
		ghost: ghost@70000000 {
			compatible = "adi,ghost";
			reg = <0x70000000 0x1000>;
		};
	};
};
&spi0 {
	status = "okay";
	adc0: adc@0 {
		compatible = "adi,ad9999";
		reg = <0>;
		clocks = <&ref_clk>, <&si570>;
		string = "not a &reference { or ; }";
	};
};
"""

# The base tree sdtgen would generate: no board file, so no I2C mux.
BASE = """
/dts-v1/;
/ {
	amba: axi {
		spi0: spi@ff040000 { };
		i2c1: i2c@ff030000 { };
		zynqmp_clk: clock-controller { };
	};
};
"""


def _topology() -> XsaTopology:
    return XsaTopology(
        fpga_part="xczu9eg-ffvb1156-2-e",
        ip_instances=[
            AxiIpInstance("axi_rx_dma", "axi_dmac", 0x9C400000, 0x1000, irq=109),
            AxiIpInstance(
                "rx_tpl_core", "ad_ip_jesd204_tpl_adc", 0x84A00000, 0x2000, irq=108
            ),
        ],
    )


def _seed():
    reference = DtsTree.parse(REFERENCE)
    return seed_design(
        reference,
        _topology(),
        DtsTree.parse(BASE),
        is_design=lambda origin: origin == "design.dts",
    )


# -- DTS source parser ------------------------------------------------------


def test_parser_tracks_origin_labels_and_overlays():
    tree = DtsTree.parse(REFERENCE)
    spi = tree.labels["spi0"]
    assert spi.origin == "board.dts"
    assert spi.properties["status"].value == '"okay"'
    assert spi.properties["status"].origin == "design.dts"
    adc = tree.labels["adc0"]
    assert adc.parent is spi and adc.origin == "design.dts"
    assert adc.path() == "/axi/spi@ff040000/adc@0"
    assert adc.references() == {"ref_clk", "si570"}
    assert tree.node_at("/axi/i2c@ff030000/i2c-mux@74/i2c@0") is not None


def test_parser_applies_delete_directives():
    tree = DtsTree.parse(
        "/ { a: one { x = <1>; y; }; two { }; };\n"
        "/delete-node/ &a;\n"
        "/ { two { /delete-property/ gone; gone; }; /delete-node/ missing; };\n"
    )
    assert [c.name for c in tree.root.children] == ["two"]
    assert "a" not in tree.labels
    assert "gone" in tree.root.child("two").properties


def test_parser_round_trips_through_render():
    tree = DtsTree.parse(REFERENCE)
    again = DtsTree.parse("/dts-v1/;\n" + tree.root.render())
    assert again.root.render() == tree.root.render()


def test_parser_rejects_unbalanced_source():
    with pytest.raises(DtsSyntaxError):
        DtsTree.parse("/ { a { x = <1>; };")
    with pytest.raises(DtsSyntaxError):
        DtsTree.parse("/ { }; };")


def test_parse_cells():
    assert parse_cells("<0 109 4>") == [0, 109, 4]
    assert parse_cells("<0x10 2>, <3>") == [16, 2, 3]
    assert parse_cells("<&clk 1>") is None
    assert parse_cells(None) is None


# -- seeding ------------------------------------------------------------------


def test_seed_ties_pl_nodes_to_xsa_instances():
    design = _seed().profile
    by_instance = {entry["instance"]: entry for entry in design["pl"]}
    assert set(by_instance) == {"axi_rx_dma", "rx_tpl_core"}
    dma = by_instance["axi_rx_dma"]
    assert dma["labels"] == ["rx_dma"] and dma["node"] == "dma-controller"
    assert dma["reg"] == [[0, 0x10000]]
    assert dma["interrupt_flags"] == 4
    assert not any(line.startswith(("reg", "interrupts")) for line in dma["body"])


def test_seed_prefers_xsa_interrupt_and_notes_the_difference():
    result = _seed()
    notes = "\n".join(result.notes)
    assert "reference interrupt 107 differs from the XSA's 108" in notes
    assert "dropped ghost@70000000" in notes


def test_seed_separates_design_content_from_the_carrier():
    design = _seed().profile
    root = "\n".join(design["root"])
    assert "ref_clk: clock@0" in root
    assert "board-regulator" not in root
    spi = next(o for o in design["overlays"] if o["target"] == "&spi0")
    assert 'status = "okay";' in spi["body"]
    assert any("adc0: adc@0" in line for line in spi["body"])
    assert not any("cdns,spi-r1p6" in line for line in spi["body"])


def test_seed_pulls_in_carrier_nodes_the_design_references():
    result = _seed()
    i2c = next(o for o in result.profile["overlays"] if o["target"] == "&i2c1")
    body = "\n".join(i2c["body"])
    # The mux chain is absent from the generated base, so it is created whole.
    assert 'compatible = "nxp,pca9548";' in body
    assert "si570: clock-generator@5d" in body
    assert result.profile["unresolved"] == []
    assert any("pulled in" in note and "si570" in note for note in result.notes)


# -- rendering ----------------------------------------------------------------


def test_builder_takes_addresses_and_interrupts_from_the_xsa():
    design = _seed().profile
    topology = _topology()
    topology.ip_instances[0].base_addr = 0x9C440000  # the HDL moved the DMA
    built = DeclarativeBuilder().build(topology, design)
    dma = built["design"][0]
    assert "rx_dma: dma-controller@9c440000 {" in dma
    assert "reg = <0x0 0x9c440000 0x0 0x10000>;" in dma
    assert "interrupts = <0 109 4>;" in dma
    assert dma.index("compatible") < dma.index("reg = ")
    core = built["design"][1]
    assert "interrupts = <0 108 4>;" in core
    assert built["replaced"] == ["axi_rx_dma", "rx_tpl_core"]
    assert built["overlays"][0].startswith("&{/} {")


def test_builder_uses_one_address_cell_on_zynq():
    topology = _topology()
    topology.fpga_part = "xc7z045ffg900-2"
    built = DeclarativeBuilder().build(topology, _seed().profile)
    assert "reg = <0x9c400000 0x10000>;" in built["design"][0]


def test_builder_rejects_a_profile_the_xsa_does_not_match():
    topology = _topology()
    topology.ip_instances.pop()
    with pytest.raises(ProfileError, match="rx_tpl_core"):
        DeclarativeBuilder().build(topology, _seed().profile)


def test_node_builder_bypasses_family_heuristics_for_declarative_designs():
    design = _seed().profile
    nodes = NodeBuilder().build(_topology(), {DESIGN_KEY: design})
    assert nodes["converters"] == [] and nodes["jesd204_rx"] == []
    assert len(nodes["design"]) == 2 + 3  # PL nodes, root, &spi0, &i2c1
    assert nodes["replaced_instances"] == ["axi_rx_dma", "rx_tpl_core"]


def test_merger_deletes_the_stubs_declarative_nodes_replace(tmp_path):
    (tmp_path / "pl.dtsi").write_text(
        "/ {\n\tamba_pl: amba_pl {\n"
        "\t\taxi_rx_dma: axi_dmac@9c400000 {\n\t\t};\n"
        "\t\tother: other@1000 {\n\t\t};\n\t};\n};\n"
    )
    base = '/dts-v1/;\n#include "pl.dtsi"\n/ {\n};\n'
    nodes = NodeBuilder().build(_topology(), {DESIGN_KEY: _seed().profile})
    _, merged = DtsMerger().merge(base, nodes, tmp_path, "demo")
    assert "/delete-node/ &axi_rx_dma;" in merged
    assert "/delete-node/ &other;" not in merged
    assert "/delete-node/ &rx_tpl_core;" not in merged  # no such stub
    assert "&amba_pl {" in merged and "rx_dma: dma-controller@9c400000" in merged
    assert "&spi0 {" in merged and "&{/} {" in merged


# -- bindings parity ------------------------------------------------------------


def test_missing_bindings_counts_enabled_adi_nodes():
    reference = DtsTree.parse(REFERENCE)
    assert adi_bindings(reference)["adi,axi-dmac-1.00.a"] == 1
    generated = DtsTree.parse(
        '/ { a { compatible = "adi,axi-dmac-1.00.a"; };'
        ' b { compatible = "adi,ad9999"; status = "disabled"; }; };'
    )
    assert missing_bindings(reference, generated) == {
        "adi,ad9999": 1,
        "adi,axi-adc-10.0.a": 1,
        "adi,ghost": 1,
    }
    assert missing_bindings(generated, reference) == {}


# -- design identity and profile selection --------------------------------------


@pytest.mark.parametrize(
    "path, expected",
    [
        (
            "/build/hdl/projects/ad9083_evb/zcu102/mem_init_sys.txt",
            ("ad9083_evb", "zcu102", ""),
        ),
        (
            "/ws/projects/dac_fmc_ebz/zcu102/ADIDACDEVICEAD9144_ADIDACMODE04/mem_init_sys.txt",
            ("dac_fmc_ebz", "zcu102", "ADIDACDEVICEAD9144_ADIDACMODE04"),
        ),
        (r"C:\hdl\projects\daq2\zc706\mem_init_sys.txt", ("daq2", "zc706", "")),
        ("/somewhere/else/rom.mem", ("", "", "")),
    ],
)
def test_parser_reads_hdl_design_identity(path, expected):
    import xml.etree.ElementTree as ET

    root = ET.fromstring(
        f'<EDKSYSTEM><MODULE><PARAMETER NAME="PATH_TO_FILE" VALUE="{path}"/>'
        "</MODULE></EDKSYSTEM>"
    )
    assert XsaParser._parse_hdl_design(root) == expected


def _write_profile(directory: Path, name: str, **design) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps({"name": name, "defaults": {}, "design": design})
    )


def test_find_design_profile_matches_identity_exactly(tmp_path):
    _write_profile(tmp_path, "p_default", project="p", carrier="zed", variant="")
    _write_profile(tmp_path, "p_lvds", project="p", carrier="zed", variant="LVDS")
    _write_profile(
        tmp_path, "p_alt", project="p", carrier="zed", variant="", default=False
    )
    (tmp_path / "legacy.json").write_text('{"name": "legacy", "defaults": {}}')
    manager = ProfileManager(tmp_path)
    assert manager.find_design_profile("p", "zed") == "p_default"
    assert manager.find_design_profile("p", "zed", "LVDS") == "p_lvds"
    assert manager.find_design_profile("p", "zed", "CMOS") is None
    assert manager.find_design_profile("p", "zc706") is None
    assert manager.find_design_profile("", "") is None


def test_pipeline_prefers_the_declared_design_profile(monkeypatch, tmp_path):
    _write_profile(tmp_path, "p_zcu102", project="p", carrier="zcu102", variant="")
    monkeypatch.setattr(
        "adidt.xsa.pipeline.ProfileManager", lambda: ProfileManager(tmp_path)
    )
    topology = _topology()
    assert XsaPipeline()._auto_profile_name(topology) is None
    topology.hdl_project, topology.hdl_carrier = "p", "zcu102"
    assert XsaPipeline()._auto_profile_name(topology) == "p_zcu102"


@pytest.mark.parametrize(
    "name, is_design",
    [
        ("zynqmp.dtsi", False),
        ("zynq-7000.dtsi", False),
        ("zynqmp-zcu102-rev1.0.dts", False),
        ("zynqmp-zcu102-revA.dts", False),
        ("zynq-zc706-adv7511.dtsi", False),
        ("zynq-zed.dtsi", False),
        ("zynqmp-zcu102-rev10-ad9083-fmc-ebz.dts", True),
        ("zynq-zc706-adv7511-ad9081.dts", True),
        ("adi-ad9083-fmc-ebz.dtsi", True),
        ("zynq-adrv9361-z7035.dtsi", True),
        ("zynq-coraz7s-axi-sysid.dtsi", True),
    ],
)
def test_design_source_file_tells_carrier_files_apart(name, is_design):
    from adidt.xsa.declarative.seed import design_source_file

    assert design_source_file(f"/kernel/arch/arm/boot/dts/xilinx/{name}") is is_design


# -- one IP backing several nodes, bus platform devices, label aliases ----------

SPLIT_REFERENCE = """
/dts-v1/;
/ {
	amba: axi {
		gic: interrupt-controller@f9010000 { };
	};
	fpga_axi: fpga-axi@0 {
		compatible = "simple-bus";
		#address-cells = <0x1>;
		#size-cells = <0x1>;
		adc_core: adc-core@79020000 {
			compatible = "adi,axi-ad9361-6.00.a";
			reg = <0x79020000 0x4000>;
			interrupt-parent = <&gic>;
			clocks = <&misc_clk>;
		};
		dac_core: dds-core@79024000 {
			compatible = "adi,axi-ad9361-dds-6.00.a";
			reg = <0x79024000 0x1000>;
		};
		misc_clk: misc-clk {
			compatible = "fixed-clock";
			#clock-cells = <0>;
		};
	};
};
"""


def _split_seed():
    topology = XsaTopology(
        fpga_part="xczu9eg-ffvb1156-2-e",
        ip_instances=[AxiIpInstance("axi_ad9361", "axi_ad9361", 0x79020000, 0x10000)],
    )
    base = DtsTree.parse("/ { amba: axi { gic_a53: interrupt-controller { }; }; };")
    result = seed_design(
        DtsTree.parse(SPLIT_REFERENCE, "design.dts"),
        topology,
        base,
        is_design=lambda origin: True,
    )
    return result, topology


def test_seed_maps_several_nodes_onto_one_ip_by_register_range():
    result, topology = _split_seed()
    adc, dac = result.profile["pl"]
    assert adc["instance"] == dac["instance"] == "axi_ad9361"
    assert "offset" not in adc and dac["offset"] == 0x4000
    assert dac["reg"] == [[0x4000, 0x1000]]
    assert not any("dropped" in note for note in result.notes)

    built = DeclarativeBuilder().build(topology, result.profile)
    assert "dac_core: dds-core@79024000 {" in built["design"][1]
    assert "reg = <0x0 0x79024000 0x0 0x1000>;" in built["design"][1]
    assert built["replaced"] == ["axi_ad9361"]


def test_seed_keeps_bus_devices_that_have_no_register_block():
    result, topology = _split_seed()
    assert result.profile["unresolved"] == []
    assert result.profile["bus"] == [
        [
            "misc_clk: misc-clk {",
            '\tcompatible = "fixed-clock";',
            "\t#clock-cells = <0>;",
            "};",
        ]
    ]
    built = DeclarativeBuilder().build(topology, result.profile)
    assert built["design"][2].startswith("\tmisc_clk: misc-clk {")


def test_seed_rewrites_labels_the_generated_base_spells_differently():
    result, _ = _split_seed()
    body = "\n".join(result.profile["pl"][0]["body"])
    assert "interrupt-parent = <&gic_a53>;" in body
    assert not any("pulled in" in note for note in result.notes)


# -- interrupt resolution ---------------------------------------------------------


def _irq_hwh(ps_type: str, ps_port: str) -> str:
    def port(name: str, signal: str, direction: str) -> str:
        return f'<PORT NAME="{name}" SIGNAME="{signal}" DIR="{direction}"/>'

    def module(instance: str, modtype: str, ports: str) -> str:
        return (
            f'<MODULE INSTANCE="{instance}" MODTYPE="{modtype}">'
            f"<PORTS>{ports}</PORTS></MODULE>"
        )

    concat_ports = port("dout", "irq_bus", "O") + "".join(
        port(f"In{n}", f"net{n}", "I") for n in range(16)
    )
    return (
        "<EDKSYSTEM>"
        + module("sys_ps", ps_type, port(ps_port, "irq_bus", "I"))
        + module("sys_concat_intc", "xlconcat", concat_ports)
        + module("axi_dma", "axi_dmac", port("irq", "net13", "O"))
        + module("axi_iic", "axi_iic", port("iic2intc_irpt", "net2", "O"))
        + module(
            "two_lines",
            "axi_ethernet",
            port("interrupt", "net4", "O") + port("mac_irq", "net5", "O"),
        )
        + module("not_an_irq", "util_thing", port("dout", "net6", "O"))
        + "</EDKSYSTEM>"
    )


def test_zynq7000_interrupts_are_resolved_from_irq_f2p():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(_irq_hwh("processing_system7", "IRQ_F2P"))
    # IRQ_F2P bits 0-7 are SPI 29-36, bits 8-15 are SPI 52-59.
    assert XsaParser()._resolve_zynqmp_irqs(root) == {"axi_dma": 57, "axi_iic": 31}


def test_zynqmp_interrupts_include_xilinx_ip_ports():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(_irq_hwh("zynq_ultra_ps_e", "pl_ps_irq1"))
    # One 8-bit bank starting at SPI 104; bit 13 is beyond it.
    assert XsaParser()._resolve_zynqmp_irqs(root) == {"axi_iic": 106}


# -- designs seeded without an XSA ------------------------------------------------


def test_seed_without_xsa_keys_pl_nodes_by_address():
    base = DtsTree.parse("/ { amba: axi { gic_a53: interrupt-controller { }; }; };")
    result = seed_design(
        DtsTree.parse(SPLIT_REFERENCE, "design.dts"),
        None,
        base,
        is_design=lambda origin: True,
    )
    adc, dac = result.profile["pl"]
    assert "instance" not in adc
    assert adc["address"] == 0x79020000 and dac["address"] == 0x79024000
    assert dac["reg"] == [[0, 0x1000]]
    assert len(result.profile["bus"]) == 1


def test_address_keyed_entries_bind_to_the_ip_in_the_xsa():
    base = DtsTree.parse("/ { amba: axi { gic_a53: interrupt-controller { }; }; };")
    design = seed_design(
        DtsTree.parse(SPLIT_REFERENCE, "design.dts"),
        None,
        base,
        is_design=lambda origin: True,
    ).profile
    topology = XsaTopology(
        fpga_part="xczu9eg-ffvb1156-2-e",
        ip_instances=[AxiIpInstance("axi_ad9361", "axi_ad9361", 0x79020000, 0x10000)],
    )
    built = DeclarativeBuilder().build(topology, design)
    assert "adc_core: axi_ad9361: adc-core@79020000 {" in built["design"][0]
    assert "dac_core: dds-core@79024000 {" in built["design"][1]
    assert "reg = <0x0 0x79024000 0x0 0x1000>;" in built["design"][1]
    assert built["replaced"] == ["axi_ad9361"]

    topology.ip_instances[0].base_addr = 0x40000000  # a different bitstream
    with pytest.raises(ProfileError, match="adc-core@79020000"):
        DeclarativeBuilder().build(topology, design)


# -- profile validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "design, reason",
    [
        ([], "expected object"),
        ({"carrier": "zed"}, "missing project"),
        ({"project": "p", "carrier": "zed", "pl": [{"node": "x"}]}, "exactly one"),
        (
            {
                "project": "p",
                "carrier": "zed",
                "pl": [{"instance": "a", "address": 4096, "node": "x"}],
            },
            "exactly one",
        ),
        (
            {"project": "p", "carrier": "zed", "pl": [{"instance": "a"}]},
            "missing node",
        ),
        (
            {
                "project": "p",
                "carrier": "zed",
                "pl": [{"instance": "a", "node": "x", "reg": [[0]]}],
            },
            "reg must be",
        ),
        ({"project": "p", "carrier": "zed", "root": "clocks { };"}, "root must be"),
        (
            {"project": "p", "carrier": "zed", "overlays": [{"target": "spi0"}]},
            "needs an &target",
        ),
    ],
)
def test_profile_manager_rejects_malformed_design(tmp_path, design, reason):
    (tmp_path / "bad.json").write_text(
        json.dumps({"name": "bad", "defaults": {}, "design": design})
    )
    with pytest.raises(ProfileError, match=reason):
        ProfileManager(tmp_path).load("bad")


def test_seeded_design_passes_profile_validation(tmp_path):
    design = {"project": "p", "carrier": "zcu102", **_seed().profile}
    (tmp_path / "good.json").write_text(
        json.dumps({"name": "good", "defaults": {}, "design": design})
    )
    assert ProfileManager(tmp_path).load("good")["design"]["project"] == "p"
