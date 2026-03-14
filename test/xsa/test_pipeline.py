# test/xsa/test_pipeline.py
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
import pytest

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.exceptions import ParityError

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


def test_pipeline_writes_manifest_parity_reports_when_reference_dts_is_provided(
    xsa_path, cfg, tmp_path
):
    reference = tmp_path / "ref.dts"
    reference.write_text(
        '/ {\n'
        '\trx0: jesd-rx@0 { compatible = "adi,axi-jesd204-rx-1.0"; };\n'
        '\tclk0: hmc7044@0 { compatible = "adi,hmc7044"; };\n'
        '};\n'
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
        '/ {\n'
        '\tclk0: hmc7044@0 { compatible = "adi,hmc7044"; };\n'
        '};\n'
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
        '/ {\n'
        '\trx0: jesd-rx@0 {\n'
        '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
        '\t\tjesd204-inputs = <&missing_xcvr 0 2>;\n'
        '\t};\n'
        '};\n'
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


def test_pipeline_strict_parity_raises_when_properties_missing(
    xsa_path, cfg, tmp_path
):
    reference = tmp_path / "ref_missing_property.dts"
    reference.write_text(
        '/ {\n'
        '\trx0: jesd-rx@0 {\n'
        '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
        '\t\tadi,missing-prop = <1>;\n'
        '\t};\n'
        '};\n'
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
        '/ {\n'
        '\trx0: jesd-rx@0 {\n'
        '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
        '\t\tadi,octets-per-frame = <99>;\n'
        '\t};\n'
        '};\n'
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
