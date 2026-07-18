"""Contract tests for the pyadi-jif -> pyadi-dt handoff."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from adidt.jif_contract import (
    ClockBinding,
    ContractError,
    JesdBinding,
    JifDtBindings,
    JifDtContract,
)


def _payload() -> dict:
    return {
        "schema": "adi.jif-dt",
        "version": "1.0",
        "producer": {"name": "pyadi-jif", "version": "0.1.6"},
        "jesd_links": [
            {
                "id": "ad9680.rx",
                "direction": "adc-to-fpga",
                "converter": "AD9680",
                "fpga": "zc706",
                "standard": "jesd204b",
                "sample_rate_hz": 1_000_000_000,
                "lane_rate_hz": 10_000_000_000,
                "parameters": {
                    "F": 1,
                    "K": 32,
                    "L": 4,
                    "M": 2,
                    "N": 16,
                    "Np": 16,
                    "S": 1,
                    "HD": 0,
                },
                "fpga_config": {"type": "qpll", "sys_clk_select": "XCVR_QPLL0"},
            }
        ],
        "clock_requirements": [
            {
                "id": "ad9680.device-clock",
                "role": "converter-device",
                "sink": "AD9680",
                "source": "HMC7044",
                "rate_hz": 1_000_000_000,
                "divider": 3,
            },
            {
                "id": "ad9680.sysref",
                "role": "converter-sysref",
                "sink": "AD9680",
                "source": "HMC7044",
                "rate_hz": 7_812_500,
                "divider": 384,
            },
        ],
        "metadata": {"solver": "CPLEX"},
    }


def _bindings() -> JifDtBindings:
    return JifDtBindings(
        clocks=(
            ClockBinding(
                requirement_id="ad9680.device-clock",
                dt_label="hmc7044",
                output_index=13,
            ),
            ClockBinding(
                requirement_id="ad9680.sysref",
                dt_label="hmc7044",
                output_index=5,
            ),
        ),
        jesd_links=(
            JesdBinding(
                link_id="ad9680.rx",
                converter_label="ad9680",
                jesd_label="axi_ad9680_jesd204_rx",
                xcvr_label="axi_ad9680_adxcvr",
            ),
        ),
    )


def test_valid_contract_binds_semantic_requirements_to_physical_dt_endpoints():
    contract = JifDtContract.model_validate(_payload())
    _bindings().check(contract)

    assert contract.clock_requirements[0].id == "ad9680.device-clock"
    assert _bindings().clocks[0].output_index == 13


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda p: p.update(version="2.0"), "version"),
        (
            lambda p: p["jesd_links"][0].update(lane_rate_hz=9_000_000_000),
            "lane_rate_hz",
        ),
        (
            lambda p: p["jesd_links"][0]["parameters"].update(F=2),
            "transport parameters",
        ),
        (
            lambda p: p["clock_requirements"][0].update(rate_hz="1000000000"),
            "int_type",
        ),
        (
            lambda p: p["clock_requirements"].append(
                dict(p["clock_requirements"][0])
            ),
            "duplicate clock requirement ids",
        ),
        (lambda p: p.update(unexpected=True), "extra_forbidden"),
    ],
)
def test_contract_rejects_incompatible_or_internally_inconsistent_data(
    mutation, match
):
    payload = _payload()
    mutation(payload)
    with pytest.raises(ValidationError, match=match):
        JifDtContract.model_validate(payload)


def test_binding_check_rejects_missing_or_unknown_semantic_ids():
    contract = JifDtContract.model_validate(_payload())
    bindings = JifDtBindings(
        clocks=(
            ClockBinding(
                requirement_id="unknown.clock", dt_label="hmc7044", output_index=0
            ),
        ),
        jesd_links=_bindings().jesd_links,
    )

    with pytest.raises(ContractError, match=r"missing=.*unknown="):
        bindings.check(contract)


def test_binding_check_rejects_two_requirements_on_one_physical_output():
    contract = JifDtContract.model_validate(_payload())
    bindings = JifDtBindings(
        clocks=(
            ClockBinding(
                requirement_id="ad9680.device-clock",
                dt_label="hmc7044",
                output_index=5,
            ),
            ClockBinding(
                requirement_id="ad9680.sysref",
                dt_label="hmc7044",
                output_index=5,
            ),
        ),
        jesd_links=_bindings().jesd_links,
    )

    with pytest.raises(ContractError, match="multiple clocks bound"):
        bindings.check(contract)


def test_json_round_trip_uses_public_schema_name(tmp_path):
    path = tmp_path / "jif-dt.json"
    contract = JifDtContract.model_validate(_payload())
    contract.to_json_file(path)

    on_disk = json.loads(path.read_text())
    assert on_disk["schema"] == "adi.jif-dt"
    assert "schema_name" not in on_disk
    assert JifDtContract.from_json_file(path) == contract


def test_json_loader_wraps_parse_and_validation_errors(tmp_path):
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{")
    with pytest.raises(ContractError, match="cannot read"):
        JifDtContract.from_json_file(malformed)

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"schema": "adi.jif-dt", "version": "1.0"}))
    with pytest.raises(ContractError, match="invalid JIF/DT contract"):
        JifDtContract.from_json_file(invalid)


def test_contract_rejects_non_json_extension_values():
    payload = _payload()
    payload["metadata"]["solver_object"] = object()

    with pytest.raises(ValidationError, match="metadata"):
        JifDtContract.model_validate(payload)
