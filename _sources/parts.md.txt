# Part Layers

To aid in device tree manipulation and integrate with other tools like **pyadi-jif**, **adidt** contais specific abstractions for different ADI parts. This is helpful for large configuration changes, which may or may not have multiple interrelated device tree nodes.

Configurations are consumed in a few ways which include json files and through stdin.

## Support Components

### Clock Generators and Distributors

- **HMC7044**: Low-jitter clock generator with integrated VCO and 14 outputs
- **AD9523-1**: Low-jitter clock generator with distribution for high-speed converters
- **AD9528**: Dual-loop clock generator with JESD204B support and integrated VCO
- **AD9545**: Quad-PLL, 10-output clock generator with integrated DPLL

### RF Transceivers and Data Converters

- **AD9081**: Quad 16-bit ADC + Dual 16-bit DAC with wideband MxFE transceiver
- **AD9084**: Multi-channel 16-bit ADC RF transceiver with JESD204C
- **ADRV9009**: Highly integrated dual-channel RF transceiver with JESD204B
- **AD9680**: Dual 14-bit, 1 GSPS ADC (used on DAQ2)
- **AD9144**: Quad 16-bit, 2.8 GSPS DAC (used on DAQ2)

### Evaluation Boards

- **DAQ2**: Reference design with AD9680, AD9144, and AD9523-1
- **AD9081-FMCA-EBZ**: AD9081 FMC board with HMC7044 clock (supports ZCU102, VPK180, ZC706)
- **AD9084-FMCA-EBZ**: AD9084 FMC board with HMC7044, ADF4382, and ADF4030 (supports VPK180, VCK190)
- **ADRV9009-FMCA-EBZ**: ADRV9009 FMC board with AD9528 clock (supports ZCU102, ZC706)
- **ADRV9009-PCB-Z**: ADRV9009 PCB evaluation board
- **ADRV9009-ZU11EG**: ADRV9009 with ZU11EG SoC

## Example with JSON from pyadi-jif

This example updates the device tree of a DAQ2 board to set the sample rate of the RX (ADC) path to 1 GSPS.

```bash
$ cat ad9523_1_jif.json
{
    "clock": {
        "m1": 3,
        "n2": 24,
        "r2": 1,
        "out_dividers": [
            2,
            128,
            8
        ],
        "output_clocks": {
            "ADC_CLK_FMC": {
                "rate": 125000000.0,
                "divider": 8
            },
            "ADC_CLK": {
                "rate": 500000000.0,
                "divider": 2
            },
            "CLKD_ADC_SYSREF": {
                "rate": 7812500.0,
                "divider": 128
            },
            "ADC_SYSREF": {
                "rate": 7812500.0,
                "divider": 128
            }
        },
        "vcxo": 125000000.0,
        "vco": 1000000000.0,
        "part": "AD9523-1"
    },
}


$ adidtc -i daq2.local -c remote_sd jif clock -f ad9523_1_jif.json
```
