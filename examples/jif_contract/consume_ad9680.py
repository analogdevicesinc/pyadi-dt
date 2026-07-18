"""Load and bind a saved AD9680 pyadi-jif handoff without a solver import."""

from __future__ import annotations

import json
from pathlib import Path

from adidt.jif_contract import JifDtBindings, JifDtContract

EXAMPLE_DIR = Path(__file__).resolve().parent


def main() -> None:
    """Validate the portable contract, then bind every semantic endpoint."""
    contract = JifDtContract.from_json_file(EXAMPLE_DIR / "ad9680.jif-dt.json")
    bindings = JifDtBindings.model_validate_json(
        (EXAMPLE_DIR / "ad9680.bindings.json").read_text()
    )
    bindings.check(contract)

    summary = {
        "schema": contract.schema_name,
        "version": contract.version,
        "links": [link.id for link in contract.jesd_links],
        "clock_bindings": {
            binding.requirement_id: {
                "dt_label": binding.dt_label,
                "output_index": binding.output_index,
            }
            for binding in bindings.clocks
        },
        "status": "validated",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
