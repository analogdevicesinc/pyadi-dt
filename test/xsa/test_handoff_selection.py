"""Scoped block designs must not hide the top-level ADI hardware topology."""

import zipfile

import pytest

from adidt.xsa.parse.topology import XsaParseError, XsaParser


@pytest.mark.parametrize("top_name", ["system.hwh", "custom_design.hwh"])
def test_manifest_selects_top_level_handoff(tmp_path, top_name):
    xsa = tmp_path / "nested.xsa"
    with zipfile.ZipFile(xsa, "w") as archive:
        archive.writestr("interconnect.hwh", "<SYSTEM />")
        archive.writestr(
            top_name,
            '<SYSTEM><MODULE MODTYPE="axi_jesd204_rx" INSTANCE="rx" /></SYSTEM>',
        )
        archive.writestr(
            "hwdef.xml",
            f'<Project><File Type="HW_HANDOFF" Name="{top_name}" BD_TYPE="DEFAULT_BD" />'
            '<File Type="HW_HANDOFF" Name="interconnect.hwh" BD_TYPE="SCOPED_BD" /></Project>',
        )
    assert XsaParser().parse(xsa).jesd204_rx[0].name == "rx"


def test_ambiguous_handoffs_are_rejected(tmp_path):
    xsa = tmp_path / "ambiguous.xsa"
    with zipfile.ZipFile(xsa, "w") as archive:
        archive.writestr("first.hwh", "<SYSTEM />")
        archive.writestr("second.hwh", "<SYSTEM />")
    with pytest.raises(XsaParseError, match="cannot identify the top-level"):
        XsaParser().parse(xsa)


def test_legacy_system_handoff_without_manifest(tmp_path):
    xsa = tmp_path / "legacy.xsa"
    with zipfile.ZipFile(xsa, "w") as archive:
        archive.writestr("interconnect.hwh", "scoped")
        archive.writestr("system.hwh", "top-level")
    assert XsaParser()._extract_hwh(xsa) == "top-level"
