"""Unit tests for the pure-Python hw_helpers parsers / validators.

These tests are hardware-independent and run as part of the normal
non-hw suite.  They exist so the ILAS parser + JESD framing validator
can be iterated on without needing a bring-up board.
"""

from __future__ import annotations

import os

import pytest

# The main test module skips at import-time unless LG_COORDINATOR /
# LG_ENV is set.  hw_helpers itself doesn't skip — import it directly.
# Ensure a skip-gating env var doesn't fire accidentally here.
os.environ.setdefault("LG_ENV", "unit-test-noop")

import test.hw.hw_helpers as hw_helpers  # noqa: E402
from test.hw.hw_helpers import (  # noqa: E402
    IlasMismatch,
    assert_ilas_aligned,
    assert_jesd_links_data,
    check_jesd_framing_plausibility,
    find_obs_capture_device,
    parse_ilas_status,
    probe_obs_enumeration,
    read_jesd_status,
)


class _FakeChannel:
    def __init__(self, *, scan_element: bool, output: bool):
        self.scan_element = scan_element
        self.output = output


class _FakeDevice:
    def __init__(self, name, *, id="", rx_scan=True):
        self.name = name
        self.id = id
        # one input scan channel when rx_scan, plus an output channel
        self.channels = []
        if rx_scan:
            self.channels.append(_FakeChannel(scan_element=True, output=False))
        self.channels.append(_FakeChannel(scan_element=True, output=True))


class _FakeCtx:
    def __init__(self, devices):
        self.devices = devices

    def find_device(self, name):
        return next((d for d in self.devices if d.name == name), None)


_DMESG_WITH_ILAS_MISMATCH = """\
[    2.123456] jesd204: ad9371-phy@1 FSM: opt_post_running_stage -> running
[    2.345678] ad9371 spi1.1: deframerStatus (0x21)
[    2.345999] ad9371 spi1.1: ILAS mismatch: c7f8
[    2.346200] ILAS lanes per converter did not match
[    2.346400] ILAS scrambling did not match
[    2.346600] ILAS octets per frame did not match
[    2.346800] ILAS frames per multiframe did not match
[    2.347000] ILAS number of converters did not match
[    2.347200] ILAS sample resolution did not match
[    2.347400] ILAS control bits per sample did not match
[    2.400000] ad9371 spi1.1: Link is disabled
"""


_DMESG_CLEAN = """\
[    2.123456] jesd204: ad9371-phy@1 FSM: opt_post_running_stage -> running
[    2.345678] ad9371 spi1.1: AD9371 Rev 3, Firmware 5.2.2 API 1.5.2.3566 initialized
[    2.400000] ad9371 spi1.1: Link is online
"""


def test_parse_ilas_status_full_mismatch():
    report = parse_ilas_status(_DMESG_WITH_ILAS_MISMATCH)
    assert report.deframer_status == 0x21
    assert report.mismatch_mask == 0xC7F8
    assert report.fields == [
        "lanes per converter",
        "scrambling",
        "octets per frame",
        "frames per multiframe",
        "number of converters",
        "sample resolution",
        "control bits per sample",
    ]
    assert report.has_mismatch is True
    assert len(report.raw_lines) == 9  # 1 status + 1 mask + 7 fields


def test_parse_ilas_status_clean_dmesg():
    report = parse_ilas_status(_DMESG_CLEAN)
    assert report.deframer_status is None
    assert report.mismatch_mask is None
    assert report.fields == []
    assert report.has_mismatch is False


def test_parse_ilas_status_mask_without_fields_still_flags():
    # Older Mykonos driver versions emit just the mask without the
    # textual per-field lines.  The mask alone must flip has_mismatch.
    dmesg = "ad9371 spi1.1: ILAS mismatch: 0x40\n"
    report = parse_ilas_status(dmesg)
    assert report.mismatch_mask == 0x40
    assert report.fields == []
    assert report.has_mismatch is True


def test_parse_ilas_status_zero_mask_is_healthy():
    # A deframerStatus dump with mask 0 should NOT flag — some kernels
    # emit the line unconditionally as diagnostic info.
    dmesg = (
        "ad9371 spi1.1: deframerStatus (0x21)\n"
        "ad9371 spi1.1: ILAS mismatch: 0\n"
    )
    report = parse_ilas_status(dmesg)
    assert report.mismatch_mask == 0
    assert report.has_mismatch is False


def test_assert_ilas_aligned_passes_on_clean():
    # Must not raise.
    assert_ilas_aligned(_DMESG_CLEAN, context="unit-test")


def test_assert_ilas_aligned_raises_on_mismatch():
    with pytest.raises(AssertionError) as excinfo:
        assert_ilas_aligned(_DMESG_WITH_ILAS_MISMATCH, context="adrv9371_xsa")
    msg = str(excinfo.value)
    assert "adrv9371_xsa" in msg
    assert "deframerStatus=0x21" in msg
    assert "mask=0xc7f8" in msg
    assert "lanes per converter" in msg


def test_check_jesd_framing_plausibility_adrv9371_hdl_defaults():
    # Documented HDL defaults include the independent observation path.
    cfg = {
        "rx": {"F": 4, "K": 32, "M": 4, "L": 2},
        "obs": {"F": 2, "K": 32, "M": 2, "L": 2},
        "tx": {"F": 2, "K": 32, "M": 4, "L": 4},
    }
    assert check_jesd_framing_plausibility(cfg) == []


def test_check_jesd_framing_plausibility_detects_typo():
    # TX F=1 is wrong for M=4/L=4/Np=16 (should be 2).
    cfg = {"tx": {"F": 1, "K": 32, "M": 4, "L": 4}}
    warnings = check_jesd_framing_plausibility(cfg)
    assert len(warnings) == 1
    assert "jesd.tx" in warnings[0]
    assert "F=1" in warnings[0]
    assert "= 2" in warnings[0]


def test_check_jesd_framing_plausibility_checks_observation_path():
    cfg = {"obs": {"F": 4, "K": 32, "M": 2, "L": 2}}
    warnings = check_jesd_framing_plausibility(cfg)
    assert len(warnings) == 1
    assert "jesd.obs" in warnings[0]


def test_check_jesd_framing_plausibility_skips_missing_fields():
    # Partial cfg must not raise or produce false warnings.
    cfg = {"rx": {"M": 4}, "tx": {}}
    assert check_jesd_framing_plausibility(cfg) == []


def test_check_jesd_framing_plausibility_handles_l_zero():
    cfg = {"rx": {"F": 4, "M": 4, "L": 0}}
    warnings = check_jesd_framing_plausibility(cfg)
    assert len(warnings) == 1
    assert "not an integer" in warnings[0]


def test_ilas_mismatch_summary_omits_none_fields():
    report = IlasMismatch(fields=["x"])
    assert "fields=[x]" in report.summary()
    assert "deframerStatus" not in report.summary()
    assert "mask" not in report.summary()


def test_assert_jesd_links_data_requires_every_expected_rx(monkeypatch):
    monkeypatch.setattr(
        hw_helpers,
        "read_jesd_status",
        lambda *_args, **_kwargs: (
            "Link status: DATA\nLink status: disabled\n",
            "Link status: DATA\n",
        ),
    )

    with pytest.raises(AssertionError, match="Expected 2 RX JESD link"):
        assert_jesd_links_data(object(), expected_rx_links=2)


def test_assert_jesd_links_data_accepts_primary_and_observation_rx(monkeypatch):
    monkeypatch.setattr(
        hw_helpers,
        "read_jesd_status",
        lambda *_args, **_kwargs: (
            "Link status: DATA\nLink status: DATA\n",
            "Link status: DATA\n",
        ),
    )

    assert_jesd_links_data(object(), expected_rx_links=2)


def test_read_jesd_status_does_not_truncate_multi_link_output():
    class FakeShell:
        def __init__(self):
            self.commands = []

        def run(self, command):
            self.commands.append(command)
            return (["Link status: DATA", "Link status: DATA"], [], 0)

    shell = FakeShell()
    rx_status, _tx_status = read_jesd_status(shell)

    assert rx_status.count("Link status: DATA") == 2
    assert all("head -n" not in command for command in shell.commands)
    assert all('echo "=== $f ==="' in command for command in shell.commands)


def test_find_obs_capture_device_prefers_named_obs():
    ctx = _FakeCtx(
        [
            _FakeDevice("ad9371-phy", rx_scan=False),
            _FakeDevice("axi-ad9371-rx-hpc"),
            _FakeDevice("axi-ad9371-rx-obs-hpc"),
        ]
    )
    dev = find_obs_capture_device(ctx)
    assert dev is not None
    assert dev.name == "axi-ad9371-rx-obs-hpc"


def test_find_obs_capture_device_matches_tpl_address_in_id():
    ctx = _FakeCtx(
        [
            _FakeDevice("axi-ad9371-rx-hpc", id="iio:device2"),
            _FakeDevice("ad_ip_jesd204_tpl_adc", id="iio:device3-44a08000"),
        ]
    )
    dev = find_obs_capture_device(ctx)
    assert dev is not None
    assert dev.id == "iio:device3-44a08000"


def test_find_obs_capture_device_ignores_control_plane_only():
    # An obs-named device with no RX scan element does not qualify.
    ctx = _FakeCtx(
        [
            _FakeDevice("axi-ad9371-rx-obs-hpc", rx_scan=False),
            _FakeDevice("axi-ad9371-rx-hpc"),
        ]
    )
    assert find_obs_capture_device(ctx) is None


def test_probe_obs_enumeration_reports_missing_obs():
    ctx = _FakeCtx(
        [
            _FakeDevice("ad9371-phy", rx_scan=False),
            _FakeDevice("axi-ad9371-rx-hpc"),
        ]
    )
    snap = probe_obs_enumeration(ctx)
    assert snap["primary_rx"] == "axi-ad9371-rx-hpc"
    assert snap["obs_device"] is None
    assert snap["obs_has_rx_scan"] is False
    assert "axi-ad9371-rx-hpc" in snap["all_devices"]


def test_probe_obs_enumeration_reports_present_obs():
    ctx = _FakeCtx(
        [
            _FakeDevice("axi-ad9371-rx-hpc"),
            _FakeDevice("axi-ad9371-rx-obs-hpc"),
        ]
    )
    snap = probe_obs_enumeration(ctx)
    assert snap["primary_rx"] == "axi-ad9371-rx-hpc"
    assert snap["obs_device"] == "axi-ad9371-rx-obs-hpc"
    assert snap["obs_has_rx_scan"] is True
