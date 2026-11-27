"""Unit tests for the release-inventory and profile-seeding scripts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def inventory_script():
    return _load("generate_hdl_release_inventory")


@pytest.fixture(scope="module")
def seed_script():
    return _load("seed_declarative_profile")


def _design(**overrides):
    design = {
        "project": "ad9083_evb",
        "carrier": "zcu102",
        "class": "jesd",
        "kuiper_projects": {"zynqmp-zcu102-rev10-ad9083-fmc-ebz": "a.dts"},
        "kuiper_projects_without_xsa": [],
        "profile": "ad9083_evb_zcu102",
        "builder": "DeclarativeBuilder",
        "status": "full",
        "reason": None,
    }
    design.update(overrides)
    return design


def test_gate_verified_boards_needs_every_boot_directory_to_pass(inventory_script):
    report = [
        {"kuiper_project": "a", "failed_stage": None, "auto_profile": "p_a"},
        {"kuiper_project": "b/CMOS", "failed_stage": None, "auto_profile": "p_b"},
        {"kuiper_project": "b/LVDS", "failed_stage": "compile", "auto_profile": "p_b"},
        {
            "kuiper_project": "c",
            "failed_stage": None,
            "auto_profile": "p_default",
            "profile": "p_c",
        },
        {"kuiper_project": "d", "failed_stage": "profile", "auto_profile": None},
    ]
    assert inventory_script.gate_verified_boards(report) == {"a": "p_a", "c": "p_c"}


def test_board_manifest_promotes_only_gate_verified_boards(inventory_script):
    inventory = {"release": "2026_r1", "designs": [_design()]}
    previous = {
        "boards": {
            "kept": {"status": "full", "profile": "hand_written", "builder": "X"},
        }
    }
    boards = inventory_script.build_kuiper_boards(
        inventory,
        ["kept", "zynqmp-zcu102-rev10-ad9083-fmc-ebz", "unknown-board"],
        previous,
        {
            "zynqmp-zcu102-rev10-ad9083-fmc-ebz": "ad9083_evb_zcu102",
            "kept": "something_else",
        },
    )["boards"]
    assert boards["kept"]["profile"] == "hand_written"  # curated entries stand
    promoted = boards["zynqmp-zcu102-rev10-ad9083-fmc-ebz"]
    assert promoted["status"] == "full"
    assert promoted["profile"] == "ad9083_evb_zcu102"
    assert promoted["builder"] == "DeclarativeBuilder"
    assert boards["unknown-board"]["status"] == "unsupported"

    unverified = inventory_script.build_kuiper_boards(
        inventory, ["zynqmp-zcu102-rev10-ad9083-fmc-ebz"], {}
    )["boards"]
    assert unverified["zynqmp-zcu102-rev10-ad9083-fmc-ebz"]["status"] != "full"


def test_locally_built_design_vouches_for_its_reference_directory(inventory_script):
    design = _design(
        project="ad9081_fmca_ebz",
        carrier="vck190",
        kuiper_projects={},
        kuiper_projects_without_xsa=[
            "versal-vck190-reva-ad9081",
            "versal-vck190-reva-ad9081-204c-txmode22-rxmode23",
        ],
        local_xsa={
            "ad9081_fmca_ebz_vck190": "arch/arm64/versal-vck190-reva-ad9081.dts"
        },
        profile="ad9081_fmca_ebz_vck190",
    )
    inventory = {"release": "2026_r1", "designs": [design]}
    report = [
        {
            "kuiper_project": "local/ad9081_fmca_ebz_vck190",
            "failed_stage": None,
            "auto_profile": "ad9081_fmca_ebz_vck190",
        },
        {"kuiper_project": "local/other", "failed_stage": None, "auto_profile": "p"},
    ]
    verified = inventory_script.gate_verified_boards(report, inventory)
    assert verified == {"versal-vck190-reva-ad9081": "ad9081_fmca_ebz_vck190"}

    stale = {"status": "unsupported", "profile": None, "builder": None}
    boards = inventory_script.build_kuiper_boards(
        inventory,
        design["kuiper_projects_without_xsa"],
        {"boards": {d: dict(stale) for d in design["kuiper_projects_without_xsa"]}},
        verified,
    )["boards"]
    assert boards["versal-vck190-reva-ad9081"]["status"] == "full"
    variant = boards["versal-vck190-reva-ad9081-204c-txmode22-rxmode23"]
    assert variant["status"] == "profile_only"
    assert variant["profile"] == "ad9081_fmca_ebz_vck190"


def test_support_doc_distinguishes_validated_from_unvalidated(inventory_script):
    inventory = {
        "release": "2026_r1",
        "hdl_ref": "origin/hdl_2026_r1",
        "hdl_commit": "4840c81f2af172b0",
        "linux_commit": "b486fe824008ce25",
        "designs": [
            _design(),
            _design(
                project="ad916x_fmc",
                kuiper_projects={},
                profile="ad916x_fmc_zcu102",
                reason="no boot files for this design in the Kuiper boot partition",
            ),
            _design(
                project="ad_quadmxfe1_ebz",
                carrier="vcu118",
                kuiper_projects={},
                profile=None,
                builder=None,
                status="unsupported",
                reason="no boot files for this design in the Kuiper boot partition",
            ),
        ],
    }
    page = inventory_script.render_support_doc(inventory)
    assert page.startswith(".. This page is generated")
    assert "HDL 2026.1 design support" in page
    assert "``hdl_2026_r1``" in page and "origin/" not in page
    assert "1 not supported, 1 profile, not validated, 1 validated of 3" in page
    rows = page.split("   * - ")
    assert "Validated" in rows[2] and "1 boot directory checked" in rows[2]
    assert "Profile, not validated" in rows[3]
    assert "Not supported" in rows[4]


def test_declared_profiles_put_the_default_first(
    inventory_script, tmp_path, monkeypatch
):
    profiles = tmp_path / "profiles"
    profiles.mkdir()

    def write(name, **design):
        (profiles / f"{name}.json").write_text(
            json.dumps({"name": name, "defaults": {}, "design": design})
        )

    write("p_zed_ad4001", project="p", carrier="zed", variant="", default=False)
    write("p_zed", project="p", carrier="zed", variant="")
    write("p_zed_lvds", project="p", carrier="zed", variant="LVDS")
    write("other", project="q", carrier="zed", variant="")
    (profiles / "legacy.json").write_text('{"name": "legacy", "defaults": {}}')
    monkeypatch.setattr(inventory_script, "CONFIG_DIR", tmp_path)
    assert inventory_script.declared_profiles("p", "zed") == [
        "p_zed",
        "p_zed_lvds",
        "p_zed_ad4001",
    ]
    profile, extras, builder, status = inventory_script.resolve_support(
        "p", "zed", ["legacy", "other", "p_zed", "p_zed_ad4001", "p_zed_lvds"]
    )
    assert (profile, builder, status) == ("p_zed", "DeclarativeBuilder", "full")
    assert extras == ["p_zed_lvds", "p_zed_ad4001"]


@pytest.mark.parametrize(
    "reference, suffix",
    [
        ("arch/arm/boot/dts/xilinx/zynq-zed-adv7511-ad4001.dts", "ad4001"),
        (
            "arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-ad9162-fmc-ebz.dts",
            "ad9162-fmc-ebz",
        ),
        (
            "arch/arm/boot/dts/xilinx/zynq-zc706-adv7511-ad9172-fmc-ebz.dts",
            "ad9172-fmc-ebz",
        ),
        ("arch/arm/boot/dts/xilinx/zynq-zed-otg.dts", "otg"),
        ("arch/arm/boot/dts/xilinx/zynq-coraz7s-ad4062.dts", "ad4062"),
    ],
)
def test_reference_suffix_drops_the_carrier_prefix(seed_script, reference, suffix):
    assert seed_script.reference_suffix(reference) == suffix


def test_profile_names_are_identifier_safe(seed_script):
    assert seed_script.profile_name("ad9083_evb", "zcu102", "") == "ad9083_evb_zcu102"
    assert (
        seed_script.profile_name("adrv9001", "zcu102", "CMOSLVDSN0")
        == "adrv9001_zcu102_cmoslvdsn0"
    )
    assert (
        seed_script.profile_name("pulsar_adc", "zed", "", suffix="ad9162-fmc-ebz")
        == "pulsar_adc_zed_ad9162_fmc_ebz"
    )


def test_default_owners_reads_seeded_profiles(seed_script, tmp_path):
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "name": "a",
                "defaults": {},
                "design": {"project": "p", "carrier": "zed", "reference": "one.dts"},
            }
        )
    )
    (tmp_path / "b.json").write_text(
        json.dumps(
            {
                "name": "b",
                "defaults": {},
                "design": {
                    "project": "p",
                    "carrier": "zed",
                    "default": False,
                    "reference": "two.dts",
                },
            }
        )
    )
    (tmp_path / "legacy.json").write_text('{"name": "legacy", "defaults": {}}')
    assert seed_script.default_owners(tmp_path) == {("p", "zed", ""): "one.dts"}
