# pyadi-dt

<a href="http://analogdevicesinc.github.io/pyadi-dt/">
<img alt="GitHub Pages" src="https://img.shields.io/badge/docs-GitHub%20Pages-blue.svg">
</a>

Device tree management tools for ADI hardware

![props command](docs/media/props.gif)

## Quick install

```bash
pip install git+https://github.com/analogdevicesinc/pyadi-dt.git
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
  -a, --arch [arm|arm64|auto]     Set target architecture which will set the
                                  target DT. auto with determine from running
                                  system  [default: auto]
  --help                          Show this message and exit.

Commands:
  jif      JIF supported updates of DT
  prop     Get and set device tree properties
  props    Get, set, and explore device tree properties
  sd-move  Move files on existing SD card
```

Use the **prop** sub command to read device tree attributes
```bash
> adidtc -c remote_sysfs -i 192.168.2.1 prop -cp adi,ad9361 clock-output-names
clock-output-names rx_sampl_clk,tx_sampl_clk
```
