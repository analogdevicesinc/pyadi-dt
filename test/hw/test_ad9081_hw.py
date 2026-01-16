import os
import pytest
import iio

# @pytest.fixture(scope="function")
# def in_bootloader(strategy, capsys):
#     with capsys.disabled():
#         strategy.transition("barebox")

    
# @pytest.fixture(scope="module")
# def iio_context(target, in_shell):
#     shell = target.get_driver("ADIShellDriver")
#     addresses = shell.get_ip_addresses()
#     ip_address = addresses[0]
#     # ip_address is of type IPv4Interface
#     ip_address = str(ip_address.ip)
#     print(f"Using IP address for IIO context: {ip_address}")
#     # Remove /24 suffix if present
#     if '/' in ip_address:
#         ip_address = ip_address.split('/')[0]
#     ctx = iio.Context(f"ip:{ip_address}")
#     assert ctx is not None, "Failed to create IIO context"
#     return ctx

@pytest.fixture(scope="module")
def post_power_off(strategy):

    yield strategy
    strategy.transition("soft_off")


# def test_shell(command, in_shell):
def test_shell(post_power_off):

    strategy = post_power_off

    strategy.transition("powered_off")

    kuiper = strategy.target.get_driver("KuiperDLDriver")

    here = os.path.dirname(os.path.abspath(__file__))

    dt_filename = os.path.join(here, 'system.dtb')

    kuiper.add_files_to_target(dt_filename)

    strategy.transition("shell")

    # Check driver is available
    shell = strategy.target.get_driver("ADIShellDriver")
    addresses = shell.get_ip_addresses()
    ip_address = addresses[0]
    ip_address = str(ip_address.ip)
    print(f"Using IP address for IIO context: {ip_address}")
    if '/' in ip_address:
        ip_address = ip_address.split('/')[0]
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    devices_to_find = ["axi-ad9081-rx-hpc"]
    for device in ctx.devices:
        print(f"Found IIO device: {device.name}")
        if device.name in devices_to_find:
            devices_to_find.remove(device.name)

    assert not devices_to_find, f"Expected IIO drivers not found: {devices_to_find}"
    
