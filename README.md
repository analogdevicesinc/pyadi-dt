# pyadi-dt

Device tree management tools for ADI hardware

![props command](docs/media/props.gif)

## Quick install

```bash
pip install git+https://github.com/tfcollins/pyadi-dt.git
```

## CLI basics

Get basic info of CLI
```bash
> adidtc
Usage: adidtc [OPTIONS] COMMAND [ARGS]...

  ADI device tree utility

Options:
  -nc, --no-color                 Disable formatting
  -c, --context [local_file|local_sd|local_sysfs|remote_sysfs|remote_sd]
                                  Set context  [default: local_sysfs]
  -i, --ip TEXT                   Set ip used by remote contexts  [default:
                                  192.168.2.1]
  -u, --username TEXT             Set username used by remote SSH sessions
                                  (default is root)  [default: root]
  -w, --password TEXT             Set password used by remote SSH sessions
                                  (default is analog)  [default: analog]
  --help                          Show this message and exit.

Commands:
  prop  Get and set device tree properties COMPATIBLE_ID - Value of..
```

Use the **prop** sub command to read device tree attributes
```bash
> adidtc -c remote_sysfs -i 192.168.2.1 prop adi,ad9361 clock-output-names
clock-output-names rx_sampl_clk,tx_sampl_clk
```
