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

from test.hw.hw_helpers import (  # noqa: E402
    IlasMismatch,
    assert_ilas_aligned,
    check_jesd_framing_plausibility,
    parse_ilas_status,
)


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
    # Documented HDL default: RX M=4 L=2 F=4, TX M=4 L=4 F=2, Np=16.
    cfg = {
        "rx": {"F": 4, "K": 32, "M": 4, "L": 2},
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
