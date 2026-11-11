"""ADRV9040 software contracts against representative HDL handoffs."""

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from adidt.devices.transceivers import ADRV9040
from adidt.xsa.build.node_builder import NodeBuilder
from adidt.xsa.config.board_configs import ADRV9040BoardConfig
from adidt.xsa.config.pipeline_config import PipelineConfig
from adidt.xsa.config.profiles import ProfileManager
from adidt.xsa.parse.topology import XsaParser
from adidt.xsa.pipeline import XsaPipeline

FIXTURES = Path(__file__).parent / "fixtures" / "adrv9040"
BASE = """/dts-v1/;
/ {
 #address-cells = <2>; #size-cells = <2>;
 zynqmp_clk: clock { #clock-cells = <1>; };
 gpio: gpio { gpio-controller; #gpio-cells = <2>; interrupt-controller; #interrupt-cells = <2>; };
 gic: interrupt-controller { interrupt-controller; #interrupt-cells = <3>; };
 spi0: spi { #address-cells = <1>; #size-cells = <0>; };
 amba_pl: axi { #address-cells = <2>; #size-cells = <2>; ranges; };
};
"""


def handoff(tmp_path, nls=False, alias="adrv904x", remove=None):
    content = (
        (FIXTURES / ("nls.hwh" if nls else "standard.hwh"))
        .read_text()
        .replace("adrv904x", alias)
    )
    if remove:
        content = re.sub(
            r'<MODULE INSTANCE="' + re.escape(remove) + r'".*?</MODULE>',
            "",
            content,
            flags=re.S,
        )
    xsa = tmp_path / "system.xsa"
    with zipfile.ZipFile(xsa, "w") as zf:
        zf.writestr("system.hwh", content)
    return xsa


def test_model_binding_and_overrides():
    text = ADRV9040(
        device_config_name="custom.bin", rx_gaintable_channel_masks=[15], reset_gpio=140
    ).render_dt(cs=0)
    assert 'compatible = "adi,adrv9040";' in text
    assert 'adi,device-config-name = "custom.bin";' in text
    assert "adi,rx-gaintable-channel-masks = <15>;" in text
    assert "reset-gpios = <&gpio 140 0>;" in text
    for name in (
        "ADRV9040_FW.bin",
        "ADRV9040_DFE_CALS_FW.bin",
        "stream_image.bin",
        "ADRV9040_RxGainTable.csv",
    ):
        assert name in text
    assert 'rx_sampl_clk", "tx_sampl_clk' in text
    assert "jesd204-link-ids = <0 2>;" in text


@pytest.mark.parametrize("nls", [False, True])
@pytest.mark.parametrize("alias", ["adrv904x", "adrv9040"])
def test_topology_profile_and_nodes(tmp_path, nls, alias):
    topo = XsaParser().parse(handoff(tmp_path, nls, alias))
    assert topo.inferred_converter_family() == "adrv9040"
    profile = "adrv9040_zcu102" + ("_nls" if nls else "")
    assert XsaPipeline()._auto_profile_name(topo) == profile
    cfg = ProfileManager().load(profile)["defaults"]
    nodes = NodeBuilder().build(topo, cfg)
    text = "\n".join(n for group in nodes.values() for n in group)
    assert "adi,axi-adc-legacy-10.0.a" in text
    assert "adi,axi-adrv904x-tx-1.0" in text
    assert "clocks = <&trx0_adrv904x 1>;" in text
    assert "<&clk0_ad9528 13>" in text
    assert "<&clk0_ad9528 3>" in text
    assert "adi,axi-data-offload-connected" in text
    assert "interrupts = <0 110 4>;" in text
    assert "interrupts = <0 107 4>;" in text
    assert "0x84a00000" in text
    assert "jesd204-link-ids = <0 2" + (" 3" if nls else "") + ">;" in text
    assert ("obs_sampl_clk" in text) is nls
    assert ("adi,axi-adrv904x-obs-1.0" in text) is nls
    labels = re.findall(r"^\s*(\w+):\s*[\w-]+(?:@\w+)?\s*{", text, re.M)
    assert len(labels) == len(set(labels))
    if nls:
        assert "DeviceProfileTest_NLS.bin" in text
        assert "clocks = <&trx0_adrv904x 2>;" in text
        assert "interrupts = <0 111 4>;" in text
    else:
        assert "DeviceProfileTest.bin" in text


@pytest.mark.parametrize("nls", [False, True])
def test_profile_mismatch_rejected(tmp_path, nls):
    topo = XsaParser().parse(handoff(tmp_path, nls))
    cfg = ProfileManager().load("adrv9040_zcu102" + ("" if nls else "_nls"))["defaults"]
    with pytest.raises(ValueError, match="observation|topology"):
        NodeBuilder().build(topo, cfg)


@pytest.mark.parametrize(
    "remove",
    [
        "axi_adrv904x_rx_os_xcvr",
        "axi_adrv904x_rx_os_dma",
        "axi_adrv904x_tx_dma",
        "rx_os_adrv904x_tpl_core_adc_tpl_core",
        "axi_adrv904x_rx_os_jesd_rx_axi",
    ],
)
def test_incomplete_layout_rejected(tmp_path, remove):
    topo = XsaParser().parse(handoff(tmp_path, True, remove=remove))
    with pytest.raises(ValueError, match="missing|incomplete"):
        NodeBuilder().build(topo, {})


def test_typed_configuration_roundtrip(tmp_path):
    cfg = PipelineConfig(
        adrv9040_board=ADRV9040BoardConfig(
            reset_gpio=141, device_config_name="mine.bin"
        )
    )
    assert PipelineConfig.from_dict(cfg.to_dict()).adrv9040_board == cfg.adrv9040_board
    text = "\n".join(
        NodeBuilder().build(XsaParser().parse(handoff(tmp_path)), cfg)["converters"]
    )
    assert "mine.bin" in text
    assert "reset-gpios = <&gpio 141 0>;" in text


@pytest.mark.parametrize("nls", [False, True])
def test_pipeline_and_dtc(tmp_path, nls):
    xsa = handoff(tmp_path, nls)

    def sdtgen(_xsa, output_dir, timeout=120):
        path = output_dir / "system-top.dts"
        path.write_text(BASE)
        return path

    with patch("adidt.xsa.pipeline.SdtgenRunner.run", side_effect=sdtgen):
        result = XsaPipeline().run(
            xsa,
            {},
            tmp_path / "out",
            emit_report=False,
            emit_clock_graphs=False,
            emit_wiring_graph=False,
        )
    expected = "adrv9040_zcu102" + ("_nls" if nls else "")
    assert result["merged"].stem == expected
    dtc = shutil.which("dtc")
    if not dtc:
        pytest.skip("dtc is required for compile validation")
    for key in ("merged", "overlay"):
        compiled = subprocess.run(
            [
                dtc,
                "-@",
                "-I",
                "dts",
                "-O",
                "dtb",
                "-o",
                str(tmp_path / f"{key}.dtb"),
                str(result[key]),
            ],
            capture_output=True,
            text=True,
        )
        assert compiled.returncode == 0, compiled.stderr


@pytest.mark.parametrize("nls", [False, True])
def test_explicit_profile_cannot_be_overridden_to_hide_mismatch(tmp_path, nls):
    xsa = handoff(tmp_path, nls)
    profile = "adrv9040_zcu102" + ("" if nls else "_nls")
    with patch("adidt.xsa.pipeline.SdtgenRunner.run") as runner:
        runner.return_value = tmp_path / "base.dts"
        runner.return_value.write_text(BASE)
        with pytest.raises(ValueError, match="profile.*topology"):
            XsaPipeline().run(
                xsa,
                {"adrv9040_board": {"observation": nls}},
                tmp_path / "out",
                profile=profile,
            )


def test_pipeline_accepts_typed_config(tmp_path):
    xsa = handoff(tmp_path)

    def sdtgen(_xsa, output_dir, timeout=120):
        path = output_dir / "system-top.dts"
        path.write_text(BASE)
        return path

    with patch("adidt.xsa.pipeline.SdtgenRunner.run", side_effect=sdtgen):
        result = XsaPipeline().run(
            xsa,
            PipelineConfig(adrv9040_board=ADRV9040BoardConfig()),
            tmp_path / "out",
            emit_report=False,
            emit_clock_graphs=False,
            emit_wiring_graph=False,
        )
    assert result["merged"].exists()


def _properties(text, label):
    """Read direct properties, applying subsequent &label overrides."""
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    props = {}
    for match in re.finditer(
        r"(?:\b" + re.escape(label) + r":\s*[^{}]+|&" + re.escape(label) + r")\s*{",
        text,
    ):
        depth = 1
        start = match.end()
        end = start
        while depth:
            depth += (text[end] == "{") - (text[end] == "}")
            end += 1
        body = text[start : end - 1]
        # Child channels are inspected separately below.
        body = re.sub(r"[^;{}]*{[^{}]*};", "", body)
        for statement in body.split(";"):
            statement = statement.strip()
            if not statement:
                continue
            key, _, value = statement.partition("=")
            props[key.strip()] = value.strip()
    return props


def _normalized(value, labels):
    for old, new in sorted(labels.items(), key=lambda item: -len(item[0])):
        value = re.sub(r"&" + re.escape(old) + r"\b", "&" + new, value)
    value = re.sub(
        r"0x[0-9a-fA-F]+|\b\d+\b",
        lambda m: str(int(m[0], 0) if m[0].startswith("0x") else int(m[0])),
        value,
    )
    return re.sub(r"\s+", "", value)


@pytest.mark.parametrize("nls", [False, True])
def test_pinned_linux_property_parity(tmp_path, nls):
    profile = ProfileManager().load("adrv9040_zcu102" + ("_nls" if nls else ""))
    assert profile["reference"]["ref"] == "22534a028813fc8e9f283b0b52dce09b05df6387"
    topo = XsaParser().parse(handoff(tmp_path, nls))
    nodes = NodeBuilder().build(topo, profile["defaults"])
    generated = "\n".join(n for group in nodes.values() for n in group)
    reference = (FIXTURES / "linux-standard.dts").read_text()
    if nls:
        reference += "\n" + (FIXTURES / "linux-nls.dts").read_text()
    defines = {
        "IRQ_TYPE_LEVEL_HIGH": "4",
        "IRQ_TYPE_EDGE_RISING": "1",
        "GPIO_ACTIVE_LOW": "1",
        "XCVR_QPLL": "3",
        "XCVR_REFCLK": "3",
    }
    for header in ("links.h", "ad9528.h"):
        defines.update(
            dict(
                re.findall(
                    r"^#define\s+(\w+)\s+(\d+)\s*$",
                    (FIXTURES / header).read_text(),
                    re.M,
                )
            )
        )
    for key, val in defines.items():
        reference = re.sub(r"\b" + key + r"\b", val, reference)
    labels = {"trx0_adrv904x": "trx0_adrv904x", "clk0_ad9528": "clk0_ad9528"}
    for path in ("rx", "tx", "rx_os") if nls else ("rx", "tx"):
        labels.update(
            {
                f"{path}_dma": f"axi_adrv904x_{path}_dma",
                f"axi_{path}_clkgen": f"axi_adrv904x_{path}_clkgen",
                f"axi_adrv904x_core_{path}": f"{path}_adrv904x_tpl_core_{'dac' if path == 'tx' else 'adc'}_tpl_core",
                f"axi_adrv904x_{path}_jesd": f"axi_adrv904x_{path}_jesd_{'tx' if path == 'tx' else 'rx'}_axi",
                f"axi_adrv904x_adxcvr_{path}": f"axi_adrv904x_{path}_xcvr",
            }
        )
    labels.update(
        {f"axi_data_offload_{p}": f"axi_adrv904x_{p}_offload" for p in ("rx", "tx")}
    )
    for old, new in labels.items():
        expected = _properties(reference, old)
        actual = _properties(generated, new)
        assert expected, old
        for key, value in expected.items():
            if key in {"clock-output-names", "reg"} and old not in {
                "trx0_adrv904x",
                "clk0_ad9528",
            }:
                if key == "reg":
                    cells = re.findall(r"0x[0-9a-fA-F]+|\b\d+\b", value)
                    assert (
                        _normalized(actual[key], {})
                        == f"<0{int(cells[0], 0)}0{int(cells[1], 0)}>"
                    )
                continue
            assert key in actual, (old, key)
            if key == "jesd204-inputs":
                assert sorted(_normalized(actual[key], {}).split(",")) == sorted(
                    _normalized(value, labels).split(",")
                ), (old, key)
            else:
                assert _normalized(actual[key], {}) == _normalized(value, labels), (
                    old,
                    key,
                    actual[key],
                    value,
                )
    for channel in (0, 1, 3, 11, 12, 13):
        expected = _properties(reference, f"ad9528_0_c{channel}")
        actual = _properties(generated, f"ad9528_0_c{channel}")
        assert actual.keys() == expected.keys()
        for key in expected:
            assert _normalized(actual[key], {}) == _normalized(expected[key], {})


def test_unrelated_explicit_profile_rejected(tmp_path):
    xsa = handoff(tmp_path)
    with patch("adidt.xsa.pipeline.SdtgenRunner.run") as runner:
        runner.return_value = tmp_path / "base.dts"
        runner.return_value.write_text(BASE)
        with pytest.raises(ValueError, match="profile.*topology"):
            XsaPipeline().run(xsa, {}, tmp_path / "out", profile="adrv9009_zcu102")


def test_irq_signal_suffix_is_not_an_interrupt_assignment(tmp_path):
    xsa = handoff(tmp_path, remove="sys_concat_intc_1")
    with zipfile.ZipFile(xsa) as zf:
        content = re.sub(
            r"irq_\d+_net", "random_signal99", zf.read("system.hwh").decode()
        )
    with zipfile.ZipFile(xsa, "w") as zf:
        zf.writestr("system.hwh", content)
    with pytest.raises(ValueError, match="interrupt route"):
        NodeBuilder().build(XsaParser().parse(xsa), {})


def test_module_local_memory_ranges_and_relocated_addresses(tmp_path):
    xsa = handoff(tmp_path)
    with zipfile.ZipFile(xsa) as zf:
        content = zf.read("system.hwh").decode()
    content = re.sub(r'(<MEMRANGE) INSTANCE="[^"]+"', r"\1", content)
    content = content.replace("0x9c400000", "0xa0400000").replace(
        "0x9c400fff", "0xa0400fff"
    )
    with zipfile.ZipFile(xsa, "w") as zf:
        zf.writestr("system.hwh", content)
    text = "\n".join(NodeBuilder().build(XsaParser().parse(xsa), {})["converters"])
    assert "reg = <0x0 0xa0400000 0x0 0x1000>;" in text
    assert "0x9c400000" not in text


@pytest.mark.parametrize("nls", [False, True])
def test_pipeline_replaces_populated_sdtgen_nodes(tmp_path, nls):
    xsa = handoff(tmp_path, nls)
    topo = XsaParser().parse(xsa)

    def sdtgen(_xsa, output_dir, timeout=120):
        stubs = "\n".join(
            f'{ip.name}: generic@{ip.base_addr:x} {{ compatible = "xlnx,stub"; reg = <0 0x{ip.base_addr:x} 0 0x{ip.size:x}>; }};'
            for ip in topo.ip_instances
        )
        base = BASE.replace("ranges; };", "ranges;\n" + stubs + "\n};")
        path = output_dir / "system-top.dts"
        path.write_text(base)
        return path

    with patch("adidt.xsa.pipeline.SdtgenRunner.run", side_effect=sdtgen):
        result = XsaPipeline().run(
            xsa,
            {},
            tmp_path / "out",
            emit_report=False,
            emit_clock_graphs=False,
            emit_wiring_graph=False,
        )
    merged = result["merged"].read_text()
    assert "xlnx,stub" not in merged
    for ip in topo.ip_instances:
        assert len(re.findall(r"\b" + re.escape(ip.name) + r":", merged)) == 1
    dtc = shutil.which("dtc")
    if dtc:
        compiled = subprocess.run(
            [
                dtc,
                "-@",
                "-I",
                "dts",
                "-O",
                "dtb",
                "-o",
                str(tmp_path / "populated.dtb"),
                str(result["merged"]),
            ],
            capture_output=True,
            text=True,
        )
        assert compiled.returncode == 0, compiled.stderr


@pytest.mark.parametrize(
    "options",
    [
        {"observation": "yes"},
        {"reset_gpio": -1},
        {"clock_cs": 0},
        {"rx_gaintable_channel_masks": [1, 2]},
        {"rx_gaintable_channel_masks": [256]},
        {"spi_max_frequency": 0},
        {"unknown_setting": 1},
    ],
)
def test_invalid_board_configuration_is_rejected(options):
    with pytest.raises(ValueError):
        ADRV9040BoardConfig.from_dict(options)


def test_jesd_and_clock_channel_overrides(tmp_path):
    topo = XsaParser().parse(handoff(tmp_path, True))
    cfg = {
        "jesd": {"rx_os": {"F": 8, "K": 64}},
        "adrv9040_board": {
            "ad9528_channels": [
                {"id": 1, "divider": 8},
                {"id": 3, "divider": 8},
                {"id": 13, "divider": 4},
            ]
        },
    }
    text = "\n".join(NodeBuilder().build(topo, cfg)["converters"])
    props = _properties(text, "axi_adrv904x_rx_os_jesd_rx_axi")
    assert props["adi,octets-per-frame"] == "<8>"
    assert props["adi,frames-per-multiframe"] == "<64>"
    assert _properties(text, "ad9528_0_c1")["adi,channel-divider"] == "<8>"


def test_first_zynqmp_interrupt_bank(tmp_path):
    xsa = handoff(tmp_path)
    with zipfile.ZipFile(xsa) as zf:
        content = zf.read("system.hwh").decode().replace("pl_ps_irq1", "pl_ps_irq0")
    with zipfile.ZipFile(xsa, "w") as zf:
        zf.writestr("system.hwh", content)
    text = "\n".join(NodeBuilder().build(XsaParser().parse(xsa), {})["converters"])
    assert "interrupts = <0 95 4>;" in text


@pytest.mark.parametrize("nls", [False, True])
def test_runnable_xsa_example(tmp_path, nls):
    import runpy

    xsa = handoff(tmp_path, nls)
    example = runpy.run_path(
        str(Path(__file__).parents[2] / "examples" / "xsa" / "adrv9040_zcu102.py")
    )

    def sdtgen(_xsa, output_dir, timeout=120):
        path = output_dir / "system-top.dts"
        path.write_text(BASE)
        return path

    with patch("adidt.xsa.pipeline.SdtgenRunner.run", side_effect=sdtgen):
        result = example["main"](
            ["--xsa", str(xsa), "--output-dir", str(tmp_path / "out")]
        )
    assert (
        "DeviceProfileTest_NLS.bin" in result["merged"].read_text()
        if nls
        else "DeviceProfileTest.bin" in result["merged"].read_text()
    )
    assert result["report"].exists()


def test_register_ranges_ignore_master_side_ddr_windows(tmp_path):
    from xml.etree import ElementTree as ET

    xsa = handoff(tmp_path)
    with zipfile.ZipFile(xsa) as zf:
        root = ET.fromstring(zf.read("system.hwh"))
    memorymap = ET.SubElement(root, "MEMORYMAP")
    for mod in root.findall(".//MODULE"):
        local = mod.find("MEMRANGE")
        if local is None:
            continue
        ET.SubElement(memorymap, "MEMRANGE", dict(local.attrib))
        local.set("INSTANCE", "sys_ps8")
        local.set("BASEVALUE", "0x0")
        local.set("HIGHVALUE", "0x7fffffff")
    with zipfile.ZipFile(xsa, "w") as zf:
        zf.writestr("system.hwh", ET.tostring(root, encoding="unicode"))
    topo = XsaParser().parse(xsa)
    dma = next(ip for ip in topo.ip_instances if ip.name == "axi_adrv904x_rx_dma")
    assert dma.base_addr == 0x9C400000
    assert dma.size == 0x1000
    NodeBuilder().build(topo, {})


def test_raw_and_typed_default_framing_are_equivalent(tmp_path):
    topo = XsaParser().parse(handoff(tmp_path, True))
    raw = "\n".join(NodeBuilder().build(topo, {})["converters"])
    typed = "\n".join(
        NodeBuilder().build(topo, PipelineConfig(adrv9040_board=ADRV9040BoardConfig()))[
            "converters"
        ]
    )
    for path in ("rx", "tx", "rx_os"):
        label = f"axi_adrv904x_{path}_jesd_{'tx' if path == 'tx' else 'rx'}_axi"
        assert _properties(raw, label) == _properties(typed, label)


def test_typed_observation_framing_roundtrips_and_preserves_explicit_values(tmp_path):
    raw = {"adrv9040_board": {}, "jesd": {"rx": {"F": 1}, "rx_os": {"F": 8, "K": 16}}}
    typed = PipelineConfig.from_dict(raw)
    assert typed.to_dict()["jesd"]["rx_os"]["F"] == 8
    topo = XsaParser().parse(handoff(tmp_path, True))
    text = "\n".join(NodeBuilder().build(topo, typed)["converters"])
    assert (
        _properties(text, "axi_adrv904x_rx_jesd_rx_axi")["adi,octets-per-frame"]
        == "<1>"
    )
    props = _properties(text, "axi_adrv904x_rx_os_jesd_rx_axi")
    assert props["adi,octets-per-frame"] == "<8>"
    assert props["adi,frames-per-multiframe"] == "<16>"


@pytest.mark.parametrize("nls", [False, True])
def test_sdtgen_controller_and_nested_bus_node_paths(tmp_path, nls):
    xsa = handoff(tmp_path, nls)
    base = BASE.replace("gic: interrupt-controller", "gic_a53: interrupt-controller")
    base = base.replace(
        "ranges; };",
        'ranges;\n uart0: serial@ff000000 {\n compatible = "xlnx,uart";\n reg = <0 0xff000000 0 0x1000>;\n };\n };',
    )

    def sdtgen(_xsa, output_dir, timeout=120):
        path = output_dir / "system-top.dts"
        path.write_text(base)
        return path

    with patch("adidt.xsa.pipeline.SdtgenRunner.run", side_effect=sdtgen):
        result = XsaPipeline().run(
            xsa,
            {},
            tmp_path / "out",
            emit_report=False,
            emit_clock_graphs=False,
            emit_wiring_graph=False,
        )
    dtc = shutil.which("dtc")
    if not dtc:
        pytest.skip("dtc required")
    blob = tmp_path / "tree.dtb"
    proc = subprocess.run(
        [dtc, "-I", "dts", "-O", "dtb", "-o", str(blob), str(result["merged"])],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    import fdt

    tree = fdt.parse_dtb(blob.read_bytes())
    assert tree.get_node("/axi/serial@ff000000")
    assert tree.get_node("/axi/axi-dmac@9c400000")
    assert tree.get_node("/axi/axi-jesd204-rx@84aa0000")
    assert "<&gic_a53>" in result["overlay"].read_text()


@pytest.mark.parametrize("only", [False, True])
def test_petalinux_pipeline_entry_points(tmp_path, only):
    xsa = handoff(tmp_path)

    def sdtgen(_xsa, output_dir, timeout=120):
        path = output_dir / "system-top.dts"
        path.write_text(BASE)
        return path

    with patch("adidt.xsa.pipeline.SdtgenRunner.run", side_effect=sdtgen) as runner:
        if only:
            result = XsaPipeline().run_petalinux_only(xsa, {}, tmp_path / "out")
            runner.assert_not_called()
        else:
            result = XsaPipeline().run(
                xsa,
                {},
                tmp_path / "out",
                output_format="petalinux",
                emit_report=False,
                emit_clock_graphs=False,
                emit_wiring_graph=False,
            )
    assert "adi,adrv9040" in result["system_user_dtsi"].read_text()
    assert result["bbappend"].exists()


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"adrv9040_board": {}, "jesd": {"rx_os": {"K": 64}}},
        {"jesd": {"rx": {"F": 1}, "rx_os": {"F": 1, "K": 64}}},
    ],
)
def test_implicit_typed_framing_matches_raw_after_auto_detection(tmp_path, raw):
    topo = XsaParser().parse(handoff(tmp_path, True))
    texts = [
        "\n".join(NodeBuilder().build(topo, cfg)["converters"])
        for cfg in (raw, PipelineConfig.from_dict(raw))
    ]
    for path in ("rx", "tx", "rx_os"):
        label = f"axi_adrv904x_{path}_jesd_{'tx' if path == 'tx' else 'rx'}_axi"
        for prop in ("adi,octets-per-frame", "adi,frames-per-multiframe"):
            assert (
                _properties(texts[0], label)[prop] == _properties(texts[1], label)[prop]
            )
