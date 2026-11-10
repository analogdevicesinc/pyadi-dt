"""Render an editable ADRV9040 device model for a custom SPI board.

Run ``python examples/adrv9040.py`` to print a PHY node. For a complete ZCU102
DTS, use ``examples/xsa/adrv9040_zcu102.py`` with the matching HDL handoff.
"""

from adidt.devices.transceivers import ADRV9040


def main():
    """Render the PHY with explicit clock/JESD connections."""
    phy = ADRV9040(device_config_name="DeviceProfileTest.bin")
    print(
        "/dts-v1/;\n/plugin/;\n&spi0 {\n\t#address-cells = <1>;\n\t#size-cells = <0>;"
    )
    print(
        phy.render_dt(
            cs=0,
            context={
                "dev_clk_ref": "clk0_ad9528 1",
                "jesd204_inputs": "<&axi_adrv904x_core_tx 0 0>, <&axi_adrv904x_rx_jesd 0 2>",
            },
        )
    )
    print("};")


if __name__ == "__main__":
    main()
