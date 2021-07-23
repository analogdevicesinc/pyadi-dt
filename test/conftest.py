import pytest

def pytest_addoption(parser):
    parser.addoption("--ip", action="store", default=None)


@pytest.fixture(scope='session')
def ip(request):
    ip_value = request.config.option.ip
    if ip_value is None:
        pytest.skip("Test requires an IP address set")
    return ip_value