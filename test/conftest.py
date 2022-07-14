import os

import pytest


def pytest_addoption(parser):
    parser.addoption("--ip", action="store", default=None)


@pytest.fixture(scope="session")
def ip(request):
    ip_value = request.config.option.ip
    if ip_value is None:
        pytest.skip("Test requires an IP address set")
    return ip_value


@pytest.fixture()
def kernel_build_config(request):
    config = {
        "branch": "master",
        "arch": "arm64",
        "repo_dir": "linux",
        "devicetree_to_test": "",
    }
    yield config

    if not os.path.isfile(config["devicetree_to_test"]):
        raise Exception(f"Device tree {config['devicetree_to_test']} not found")
    target = os.path.abspath(config["devicetree_to_test"])

    if config["arch"] == "arm64":
        compiler = "aarch64-linux-gnu-"
        defconfig = "adi_zynqmp_defconfig"
    elif config["arch"] == "arm32":
        compiler = "arm-linux-gnueabihf-"
        defconfig = "zynq_xcomm_adv7511_defconfig"
    else:
        raise ValueError(f"Unknown arch {config['arch']}")
    target_copy = f"arch/{config['arch']}/boot/dts/xilinx/"

    if not os.path.isdir(config["repo_dir"]):
        os.system(
            f'git clone https://github.com/analogdevicesinc/linux.git --depth=1 -b {config["branch"]} {config["repo_dir"]}'
        )
    # Build the kernel
    os.chdir(config["repo_dir"])

    cmd = f'make CROSS_COMPILE={compiler} ARCH={config["arch"]} {defconfig}'
    print(f"Running: {cmd}")
    os.system(cmd)
    cmd = f'make CROSS_COMPILE={compiler} ARCH={config["arch"]} -j'
    print(f"Running: {cmd}")
    os.system(cmd)

    # Copy in generated devicetree
    e = os.system(f"cp {target} {target_copy}")
    if e != 0:
        raise Exception(f"Failed to copy {target} to {target_copy}")

    dts_filename = os.path.basename(target)

    # Build the device tree
    cmd = f"make CROSS_COMPILE={compiler} ARCH={config['arch']} xilinx/{dts_filename.replace('.dts', '.dtb')}"
    print(f"Running: {cmd}")
    e = os.system(cmd)
    if e != 0:
        raise Exception(f"Failed to build device tree {dts_filename}")
