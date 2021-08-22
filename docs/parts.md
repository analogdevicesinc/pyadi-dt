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
{'compatible': 'adi,ad9523-1',
 'm1': 3.0,
 'n2': 24,
 'out_dividers': [1.0, 2.0, 128.0],
 'output_clocks': {'ADC': {'divider': 1.0, 'rate': 1000000000.0},
                   'FPGA': {'divider': 2.0, 'rate': 500000000.0},
                   'SYSREF': {'divider': 128.0, 'rate': 7812500.0}},
 'r2': 1.0,
 'vcxo': 125000000.0}

$ adidtc -i daq2.local -c remote_sd prop -j ad9523_1_jif.json -r
```
