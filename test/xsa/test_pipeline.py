# test/xsa/test_pipeline.py
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
import pytest

from adidt.xsa.pipeline import XsaPipeline

FIXTURE_HWH = Path(__file__).parent / "fixtures" / "ad9081_zcu102.hwh"
FIXTURE_CFG = Path(__file__).parent / "fixtures" / "ad9081_config.json"


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
    dts.write_text("/dts-v1/;\n/ {\n\tamba: axi {\n\t\t#address-cells = <2>;\n\t};\n};\n")
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
