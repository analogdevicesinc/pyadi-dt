# test/xsa/test_pipeline.py
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
import pytest

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.exceptions import ParityError
from adidt.xsa.parity import ParityReport

FIXTURE_HWH = Path(__file__).parent / "fixtures" / "ad9081_zcu102.hwh"
FIXTURE_CFG = Path(__file__).parent / "fixtures" / "ad9081_config.json"
FIXTURE_GOLDEN_MERGED = (
    Path(__file__).parent / "fixtures" / "ad9081_pipeline_merged_golden.dts"
)


@pytest.fixture
def xsa_path(tmp_path):
    xsa = tmp_path / "design.xsa"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.write(FIXTURE_HWH, "design.hwh")
    xsa.write_bytes(buf.getvalue())
    return xsa


@pytest.fixture
def cfg():
    return json.loads(FIXTURE_CFG.read_text())


def _fake_sdtgen_run(xsa_path, output_dir, timeout=120):
    dts = output_dir / "system-top.dts"
    dts.write_text(
        "/dts-v1/;\n/ {\n\tamba: axi {\n\t\t#address-cells = <2>;\n\t};\n};\n"
    )
    return dts


def test_pipeline_produces_overlay_and_merged(xsa_path, cfg, tmp_path):
    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        result = XsaPipeline().run(xsa_path, cfg, tmp_path)
    assert result["overlay"].exists()
    assert result["merged"].exists()
    assert result["report"].exists()


def test_pipeline_output_names_derived_from_converter(xsa_path, cfg, tmp_path):
    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        result = XsaPipeline().run(xsa_path, cfg, tmp_path)
    assert "ad9081" in result["overlay"].name


def test_pipeline_merged_matches_golden_snapshot(xsa_path, cfg, tmp_path):
    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        result = XsaPipeline().run(xsa_path, cfg, tmp_path)

    merged = result["merged"].read_text()
    golden = FIXTURE_GOLDEN_MERGED.read_text()
    assert merged == golden


def test_pipeline_profile_defaults_are_applied_without_overriding_explicit_cfg(
    xsa_path, cfg, tmp_path
):
    captured_cfg = {}

    class _FakeNodeBuilder:
        def build(self, topology, in_cfg):
            captured_cfg["cfg"] = in_cfg
            return {"clkgens": [], "jesd204_rx": [], "jesd204_tx": [], "converters": []}

    with (
        patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner,
        patch("adidt.xsa.pipeline.NodeBuilder", return_value=_FakeNodeBuilder()),
    ):
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        cfg_local = dict(cfg)
        cfg_local["clock"] = dict(cfg_local.get("clock", {}))
        cfg_local["clock"]["hmc7044_rx_channel"] = 22
        XsaPipeline().run(xsa_path, cfg_local, tmp_path, profile="ad9081_zcu102")

    merged_cfg = captured_cfg["cfg"]
    assert merged_cfg["clock"]["hmc7044_rx_channel"] == 22
    assert "hmc7044_tx_channel" in merged_cfg["clock"]
    assert merged_cfg["ad9081_board"]["clock_spi"] == "spi1"
    assert merged_cfg["ad9081_board"]["adc_spi"] == "spi0"


def test_pipeline_auto_selects_matching_builtin_profile(xsa_path, cfg, tmp_path):
    captured_cfg = {}

    class _FakeNodeBuilder:
        def build(self, topology, in_cfg):
            captured_cfg["cfg"] = in_cfg
            return {"clkgens": [], "jesd204_rx": [], "jesd204_tx": [], "converters": []}

    with (
        patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner,
        patch("adidt.xsa.pipeline.NodeBuilder", return_value=_FakeNodeBuilder()),
    ):
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        XsaPipeline().run(xsa_path, cfg, tmp_path)

    merged_cfg = captured_cfg["cfg"]
    assert merged_cfg["ad9081_board"]["clock_spi"] == "spi1"
    assert merged_cfg["ad9081_board"]["adc_spi"] == "spi0"


def test_pipeline_explicit_adrv9008_profile_applies_defaults(xsa_path, cfg, tmp_path):
    captured_cfg = {}

    class _FakeNodeBuilder:
        def build(self, topology, in_cfg):
            captured_cfg["cfg"] = in_cfg
            return {"clkgens": [], "jesd204_rx": [], "jesd204_tx": [], "converters": []}

    with (
        patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner,
        patch("adidt.xsa.pipeline.NodeBuilder", return_value=_FakeNodeBuilder()),
    ):
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        XsaPipeline().run(xsa_path, cfg, tmp_path, profile="adrv9008_zcu102")

    merged_cfg = captured_cfg["cfg"]
    assert merged_cfg["adrv9009_board"]["spi_bus"] == "spi0"
    assert merged_cfg["adrv9009_board"]["clk_cs"] == 0
    assert merged_cfg["adrv9009_board"]["trx_cs"] == 1


def test_pipeline_explicit_profile_controls_output_names(xsa_path, cfg, tmp_path):
    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        result = XsaPipeline().run(xsa_path, cfg, tmp_path, profile="adrv9008_zcu102")
    assert result["overlay"].name == "adrv9008_zcu102.dtso"
    assert result["merged"].name == "adrv9008_zcu102.dts"
    assert result["report"].name == "adrv9008_zcu102_report.html"


def test_pipeline_auto_selects_fmcdaq2_zc706_profile(tmp_path):
    xsa = tmp_path / "fmcdaq2_zc706.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER><DEVICE Name="xc7z045" Package="ffg900" SpeedGrade="-2"/></HEADER>
  <MODULES>
    <MODULE MODTYPE="axi_ad9680" INSTANCE="axi_ad9680_0">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x44A10000" HIGHVALUE="0x44A1FFFF"/></MEMORYMAP>
    </MODULE>
    <MODULE MODTYPE="axi_ad9144" INSTANCE="axi_ad9144_0">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x44A20000" HIGHVALUE="0x44A2FFFF"/></MEMORYMAP>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    captured_cfg = {}

    class _FakeNodeBuilder:
        def build(self, topology, in_cfg):
            captured_cfg["cfg"] = in_cfg
            return {"clkgens": [], "jesd204_rx": [], "jesd204_tx": [], "converters": []}

    with (
        patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner,
        patch("adidt.xsa.pipeline.NodeBuilder", return_value=_FakeNodeBuilder()),
    ):
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        XsaPipeline().run(xsa, cfg={}, output_dir=tmp_path / "out")

    merged_cfg = captured_cfg["cfg"]
    assert merged_cfg["fmcdaq2_board"]["spi_bus"] == "spi0"
    assert merged_cfg["fmcdaq2_board"]["clock_cs"] == 0


def test_pipeline_auto_selects_fmcdaq2_zcu102_profile(tmp_path):
    xsa = tmp_path / "fmcdaq2_zcu102.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER><DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/></HEADER>
  <MODULES>
    <MODULE MODTYPE="axi_ad9680" INSTANCE="axi_ad9680_0">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84A10000" HIGHVALUE="0x84A1FFFF"/></MEMORYMAP>
    </MODULE>
    <MODULE MODTYPE="axi_ad9144" INSTANCE="axi_ad9144_0">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84A20000" HIGHVALUE="0x84A2FFFF"/></MEMORYMAP>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    captured_cfg = {}

    class _FakeNodeBuilder:
        def build(self, topology, in_cfg):
            captured_cfg["cfg"] = in_cfg
            return {"clkgens": [], "jesd204_rx": [], "jesd204_tx": [], "converters": []}

    with (
        patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner,
        patch("adidt.xsa.pipeline.NodeBuilder", return_value=_FakeNodeBuilder()),
    ):
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        XsaPipeline().run(xsa, cfg={}, output_dir=tmp_path / "out")

    merged_cfg = captured_cfg["cfg"]
    assert merged_cfg["fmcdaq2_board"]["spi_bus"] == "spi0"
    assert merged_cfg["fmcdaq2_board"]["clock_cs"] == 0


def test_pipeline_auto_selects_fmcdaq2_profile_from_jesd_labels_only(tmp_path):
    xsa = tmp_path / "fmcdaq2_jesd_only.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER><DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/></HEADER>
  <MODULES>
    <MODULE MODTYPE="ad_ip_jesd204_tpl_adc" INSTANCE="ad9680_tpl_core_adc_tpl_core">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84A10000" HIGHVALUE="0x84A11FFF"/></MEMORYMAP>
    </MODULE>
    <MODULE MODTYPE="ad_ip_jesd204_tpl_dac" INSTANCE="ad9144_tpl_core_dac_tpl_core">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84A20000" HIGHVALUE="0x84A21FFF"/></MEMORYMAP>
    </MODULE>
    <MODULE MODTYPE="axi_jesd204_rx" INSTANCE="axi_ad9680_jesd_rx_axi">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84AA0000" HIGHVALUE="0x84AA3FFF"/></MEMORYMAP>
      <PARAMETERS><PARAMETER NAME="NUM_LANES" VALUE="4"/></PARAMETERS>
      <PORTS><PORT NAME="core_clk" SIGNAME="rx_clk"/></PORTS>
    </MODULE>
    <MODULE MODTYPE="axi_jesd204_tx" INSTANCE="axi_ad9144_jesd_tx_axi">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84A90000" HIGHVALUE="0x84A93FFF"/></MEMORYMAP>
      <PARAMETERS><PARAMETER NAME="NUM_LANES" VALUE="4"/></PARAMETERS>
      <PORTS><PORT NAME="core_clk" SIGNAME="tx_clk"/></PORTS>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    captured_cfg = {}

    class _FakeNodeBuilder:
        def build(self, topology, in_cfg):
            captured_cfg["cfg"] = in_cfg
            return {"clkgens": [], "jesd204_rx": [], "jesd204_tx": [], "converters": []}

    with (
        patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner,
        patch("adidt.xsa.pipeline.NodeBuilder", return_value=_FakeNodeBuilder()),
    ):
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        XsaPipeline().run(xsa, cfg={}, output_dir=tmp_path / "out")

    merged_cfg = captured_cfg["cfg"]
    assert merged_cfg["fmcdaq2_board"]["spi_bus"] == "spi0"


def test_pipeline_auto_selects_adrv9025_profile_from_adrv9026_jesd_names(tmp_path):
    xsa = tmp_path / "adrv9025_jesd_only.xsa"
    hwh_content = """<?xml version="1.0"?>
<EDKPROJECT>
  <HEADER><DEVICE Name="xczu9eg" Package="ffvb1156" SpeedGrade="-2"/></HEADER>
  <MODULES>
    <MODULE MODTYPE="ad_ip_jesd204_tpl_adc" INSTANCE="rx_adrv9026_tpl_core_adc_tpl_core">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84AA0000" HIGHVALUE="0x84AA3FFF"/></MEMORYMAP>
    </MODULE>
    <MODULE MODTYPE="ad_ip_jesd204_tpl_dac" INSTANCE="tx_adrv9026_tpl_core_dac_tpl_core">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84A90000" HIGHVALUE="0x84A93FFF"/></MEMORYMAP>
    </MODULE>
    <MODULE MODTYPE="axi_jesd204_rx" INSTANCE="axi_adrv9026_rx_jesd_rx_axi">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84AB0000" HIGHVALUE="0x84AB3FFF"/></MEMORYMAP>
      <PARAMETERS><PARAMETER NAME="NUM_LANES" VALUE="4"/></PARAMETERS>
      <PORTS><PORT NAME="core_clk" SIGNAME="rx_clk"/></PORTS>
    </MODULE>
    <MODULE MODTYPE="axi_jesd204_tx" INSTANCE="axi_adrv9026_tx_jesd_tx_axi">
      <MEMORYMAP><MEMRANGE BASEVALUE="0x84AC0000" HIGHVALUE="0x84AC3FFF"/></MEMORYMAP>
      <PARAMETERS><PARAMETER NAME="NUM_LANES" VALUE="4"/></PARAMETERS>
      <PORTS><PORT NAME="core_clk" SIGNAME="tx_clk"/></PORTS>
    </MODULE>
  </MODULES>
</EDKPROJECT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("design.hwh", hwh_content)
    xsa.write_bytes(buf.getvalue())

    captured_cfg = {}

    class _FakeNodeBuilder:
        def build(self, topology, in_cfg):
            captured_cfg["cfg"] = in_cfg
            return {"clkgens": [], "jesd204_rx": [], "jesd204_tx": [], "converters": []}

    with (
        patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner,
        patch("adidt.xsa.pipeline.NodeBuilder", return_value=_FakeNodeBuilder()),
    ):
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        XsaPipeline().run(xsa, cfg={}, output_dir=tmp_path / "out")

    merged_cfg = captured_cfg["cfg"]
    assert merged_cfg["adrv9009_board"]["spi_bus"] == "spi0"
    assert merged_cfg["adrv9009_board"]["clk_cs"] == 0


def test_pipeline_derive_name_handles_mxfe_jesd_only():
    from adidt.xsa.topology import Jesd204Instance, XsaTopology

    topo = XsaTopology(
        fpga_part="xczu9eg_ffvb1156_-2",
        jesd204_rx=[
            Jesd204Instance(
                name="axi_mxfe_rx_jesd_rx_axi",
                base_addr=0x84A90000,
                num_lanes=4,
                irq=None,
                link_clk="rx_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_mxfe_tx_jesd_tx_axi",
                base_addr=0x84B90000,
                num_lanes=4,
                irq=None,
                link_clk="tx_clk",
                direction="tx",
            )
        ],
    )
    assert XsaPipeline()._derive_name(topo) == "ad9081_zcu102"


def test_pipeline_derive_name_handles_ad9084_jesd_only():
    from adidt.xsa.topology import Jesd204Instance, XsaTopology

    topo = XsaTopology(
        fpga_part="xcvp1202_vsva2785_-2MHP-e-S",
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9084_rx_jesd_rx_axi",
                base_addr=0xA4000000,
                num_lanes=8,
                irq=None,
                link_clk="rx_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9084_tx_jesd_tx_axi",
                base_addr=0xA5000000,
                num_lanes=8,
                irq=None,
                link_clk="tx_clk",
                direction="tx",
            )
        ],
    )
    assert XsaPipeline()._derive_name(topo) == "ad9084_vpk180"


def test_pipeline_derive_name_ignores_unknown_converter_when_known_exists():
    from adidt.xsa.topology import ConverterInstance, XsaTopology

    topo = XsaTopology(
        fpga_part="xczu9eg_ffvb1156_-2",
        converters=[
            ConverterInstance(
                name="axi_unknown_0",
                ip_type="axi_unknown_chip",
                base_addr=0x84A00000,
                spi_bus=None,
                spi_cs=None,
            ),
            ConverterInstance(
                name="axi_adrv9009_0",
                ip_type="axi_adrv9009",
                base_addr=0x84A10000,
                spi_bus=None,
                spi_cs=None,
            ),
        ],
    )
    assert XsaPipeline()._derive_name(topo) == "adrv9009_zcu102"


def test_pipeline_derive_name_uses_substring_platform_inference():
    from adidt.xsa.topology import XsaTopology

    topo = XsaTopology(
        fpga_part="xilinx,xcvp1202,revA",
    )
    assert XsaPipeline()._derive_name(topo) == "unknown_vpk180"


def test_pipeline_derive_name_uses_adrv9025_family_for_adrv9026_labels():
    from adidt.xsa.topology import Jesd204Instance, XsaTopology

    topo = XsaTopology(
        fpga_part="xczu9eg_ffvb1156_-2",
        jesd204_rx=[
            Jesd204Instance(
                name="axi_adrv9026_rx_jesd_rx_axi",
                base_addr=0x84AB0000,
                num_lanes=4,
                irq=None,
                link_clk="rx_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_adrv9026_tx_jesd_tx_axi",
                base_addr=0x84AC0000,
                num_lanes=4,
                irq=None,
                link_clk="tx_clk",
                direction="tx",
            )
        ],
    )
    assert XsaPipeline()._derive_name(topo) == "adrv9025_zcu102"


def test_pipeline_derive_name_uses_adrv937x_family_for_ad9371_labels():
    from adidt.xsa.topology import Jesd204Instance, XsaTopology

    topo = XsaTopology(
        fpga_part="xczu9eg_ffvb1156_-2",
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9371_rx_jesd_rx_axi",
                base_addr=0x84AB0000,
                num_lanes=4,
                irq=None,
                link_clk="rx_clk",
                direction="rx",
            )
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9371_tx_jesd_tx_axi",
                base_addr=0x84AC0000,
                num_lanes=4,
                irq=None,
                link_clk="tx_clk",
                direction="tx",
            )
        ],
    )
    assert XsaPipeline()._derive_name(topo) == "adrv937x_zcu102"


def test_pipeline_writes_manifest_parity_reports_when_reference_dts_is_provided(
    xsa_path, cfg, tmp_path
):
    reference = tmp_path / "ref.dts"
    reference.write_text(
        "/ {\n"
        '\trx0: jesd-rx@0 { compatible = "adi,axi-jesd204-rx-1.0"; };\n'
        '\tclk0: hmc7044@0 { compatible = "adi,hmc7044"; };\n'
        "};\n"
    )

    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        result = XsaPipeline().run(xsa_path, cfg, tmp_path, reference_dts=reference)

    assert result["map"].exists()
    assert result["coverage"].exists()
    map_data = json.loads(result["map"].read_text())
    assert map_data["total_roles"] >= 2
    assert "missing_roles" in map_data


def test_pipeline_strict_parity_raises_when_roles_missing(xsa_path, cfg, tmp_path):
    reference = tmp_path / "ref_missing.dts"
    reference.write_text(
        '/ {\n\tclk0: hmc7044@0 { compatible = "adi,hmc7044"; };\n};\n'
    )

    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        with pytest.raises(ParityError, match="missing required roles"):
            XsaPipeline().run(
                xsa_path,
                cfg,
                tmp_path,
                reference_dts=reference,
                strict_parity=True,
            )


def test_pipeline_strict_parity_raises_when_links_missing(xsa_path, cfg, tmp_path):
    reference = tmp_path / "ref_missing_link.dts"
    reference.write_text(
        "/ {\n"
        "\trx0: jesd-rx@0 {\n"
        '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
        "\t\tjesd204-inputs = <&missing_xcvr 0 2>;\n"
        "\t};\n"
        "};\n"
    )

    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        with pytest.raises(ParityError, match="missing required links"):
            XsaPipeline().run(
                xsa_path,
                cfg,
                tmp_path,
                reference_dts=reference,
                strict_parity=True,
            )


def test_pipeline_strict_parity_raises_when_properties_missing(xsa_path, cfg, tmp_path):
    reference = tmp_path / "ref_missing_property.dts"
    reference.write_text(
        "/ {\n"
        "\trx0: jesd-rx@0 {\n"
        '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
        "\t\tadi,missing-prop = <1>;\n"
        "\t};\n"
        "};\n"
    )

    with patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner:
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        with pytest.raises(ParityError, match="missing required properties"):
            XsaPipeline().run(
                xsa_path,
                cfg,
                tmp_path,
                reference_dts=reference,
                strict_parity=True,
            )


def test_pipeline_strict_parity_raises_when_property_values_mismatch(
    xsa_path, cfg, tmp_path
):
    reference = tmp_path / "ref_property_value.dts"
    reference.write_text(
        "/ {\n"
        "\trx0: jesd-rx@0 {\n"
        '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
        "\t\tadi,octets-per-frame = <99>;\n"
        "\t};\n"
        "};\n"
    )

    mocked_report = ParityReport(
        total_roles=0,
        matched_roles=0,
        total_links=0,
        matched_links=0,
        total_properties=1,
        matched_properties=0,
        mismatched_properties=["rx0.adi,octets-per-frame: expected <99>, got <8>"],
    )

    with (
        patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner,
        patch(
            "adidt.xsa.pipeline.check_manifest_against_dts", return_value=mocked_report
        ),
    ):
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        with pytest.raises(ParityError, match="mismatched required properties"):
            XsaPipeline().run(
                xsa_path,
                cfg,
                tmp_path,
                reference_dts=reference,
                strict_parity=True,
            )


def test_pipeline_strict_parity_reports_multiple_gap_categories(
    xsa_path, cfg, tmp_path
):
    reference = tmp_path / "ref.dts"
    reference.write_text('/ { model = "x"; };\n')

    mocked_report = ParityReport(
        total_roles=1,
        matched_roles=0,
        total_links=1,
        matched_links=0,
        total_properties=1,
        matched_properties=0,
        missing_roles=["clock_chip:clk0"],
        missing_links=["rx0.jesd204-inputs->xcvr0"],
        missing_properties=["rx0.adi,octets-per-frame=<4>"],
    )

    with (
        patch("adidt.xsa.pipeline.SdtgenRunner") as MockRunner,
        patch(
            "adidt.xsa.pipeline.check_manifest_against_dts", return_value=mocked_report
        ),
    ):
        MockRunner.return_value.run.side_effect = _fake_sdtgen_run
        with pytest.raises(ParityError) as ex:
            XsaPipeline().run(
                xsa_path,
                cfg,
                tmp_path,
                reference_dts=reference,
                strict_parity=True,
            )

    msg = str(ex.value)
    assert "missing required roles" in msg
    assert "missing required links" in msg
    assert "missing required properties" in msg
