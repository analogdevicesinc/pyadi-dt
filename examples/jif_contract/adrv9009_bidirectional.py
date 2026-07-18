"""Build and bind a bidirectional ADRV9009 contract in memory."""

from __future__ import annotations

import json

from adidt.jif_contract import (
    ClockBinding,
    ClockRequirement,
    JesdBinding,
    JesdLink,
    JesdParameters,
    JifDtBindings,
    JifDtContract,
    Producer,
)


def build_contract() -> JifDtContract:
    """Return solved RX/TX electrical intent with no physical DT placement."""
    return JifDtContract(
        schema="adi.jif-dt",
        producer=Producer(version="0.1.6"),
        jesd_links=(
            JesdLink(
                id="adrv9009.rx",
                direction="adc-to-fpga",
                converter="ADRV9009_RX",
                fpga="zcu102",
                standard="jesd204b",
                sample_rate_hz=245_760_000,
                lane_rate_hz=9_830_400_000,
                parameters=JesdParameters(
                    F=4, K=32, L=2, M=4, N=16, Np=16, S=1, HD=0
                ),
                fpga_config={"type": "qpll"},
            ),
            JesdLink(
                id="adrv9009.tx",
                direction="fpga-to-dac",
                converter="ADRV9009_TX",
                fpga="zcu102",
                standard="jesd204b",
                sample_rate_hz=245_760_000,
                lane_rate_hz=4_915_200_000,
                parameters=JesdParameters(
                    F=2, K=32, L=4, M=4, N=16, Np=16, S=1, HD=0
                ),
                fpga_config={"type": "qpll"},
            ),
        ),
        clock_requirements=(
            ClockRequirement(
                id="adrv9009.device-clock",
                role="converter-device",
                sink="ADRV9009",
                source="AD9528",
                rate_hz=245_760_000,
                divider=4,
            ),
            ClockRequirement(
                id="adrv9009.sysref",
                role="converter-sysref",
                sink="ADRV9009",
                source="AD9528",
                rate_hz=7_680_000,
                divider=128,
            ),
        ),
        metadata={"example": "bidirectional ADRV9009 on ZCU102"},
    )


def build_bindings() -> JifDtBindings:
    """Return the independent pyadi-dt board placement for the solved intent."""
    return JifDtBindings(
        clocks=(
            ClockBinding(
                requirement_id="adrv9009.device-clock",
                dt_label="ad9528",
                output_index=1,
            ),
            ClockBinding(
                requirement_id="adrv9009.sysref",
                dt_label="ad9528",
                output_index=3,
            ),
        ),
        jesd_links=(
            JesdBinding(
                link_id="adrv9009.rx",
                converter_label="adrv9009-phy",
                jesd_label="axi_adrv9009_rx_jesd",
                xcvr_label="axi_adrv9009_rx_xcvr",
            ),
            JesdBinding(
                link_id="adrv9009.tx",
                converter_label="adrv9009-phy",
                jesd_label="axi_adrv9009_tx_jesd",
                xcvr_label="axi_adrv9009_tx_xcvr",
            ),
        ),
    )


def main() -> None:
    """Validate both link directions before any pipeline or DT operation."""
    contract = build_contract()
    bindings = build_bindings()
    bindings.check(contract)

    print(
        json.dumps(
            {
                "links": {
                    link.id: {
                        "direction": link.direction,
                        "lane_rate_hz": link.lane_rate_hz,
                    }
                    for link in contract.jesd_links
                },
                "status": "validated",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
