"""Clock handles and emitted bindings must agree on the output driver mode."""

import pytest

from adidt.devices.clocks import AD9528, AD9528Channel, AD9528_1Channel


@pytest.mark.parametrize(
    "channel_type,default", [(AD9528Channel, 3), (AD9528_1Channel, 0)]
)
def test_driver_mode_default_and_override_are_rendered(channel_type, default):
    for mode in (default, 2):
        channel = (
            channel_type(id=4)
            if mode == default
            else channel_type(id=4, driver_mode=mode)
        )
        clock = AD9528(channels={4: channel})
        rendered = clock.render_dt(cs=0)
        assert rendered.count("adi,driver-mode") == 1
        assert f"adi,driver-mode = <{mode}>;" in rendered
        assert clock._build_clock_outputs()[0].driver_mode == mode
