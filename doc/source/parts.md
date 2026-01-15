# Part Layers

To aid in device tree manipulation and integrate with other tools like **pyadi-jif**, **adidt** contais specific abstractions for different ADI parts. This is helpful for large configuration changes, which may or may not have multiple interrelated device tree nodes.

Configurations are consumed in a few ways which include json files and through stdin.

## Support Components

- HMC7044
- AD9680
- AD9144
- AD9523-1
- DAQ2 (AD9680, AD9144, AD9523-1)

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
