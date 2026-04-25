"""Reusable pre-capture hooks and capture-target resolvers.

Hooks here are wired into a :class:`BoardOverlayProfile` via
``pre_capture_hook`` / ``capture_targets_resolver`` slots when the
generic flow needs a per-family adjustment.  Anything truly board-
specific (single-board diagnostic prints, baked-DTB profile loads)
stays in the board test file.
"""

from __future__ import annotations

import base64
import time
import urllib.request
from pathlib import Path

from test.hw.hw_helpers import shell_out


# ---------------------------------------------------------------------------
# Talise profile push (ADRV9009 family)
# ---------------------------------------------------------------------------

# Smallest of the canonical Talise filter profiles iio-oscilloscope ships.
# All four use ``deviceClock=245.76 MHz``, so pushing this profile re-inits
# the Talise radio to a state where buffered RX is enabled without
# changing the JESD lane rate.
_TALISE_PROFILE_URL = (
    "https://raw.githubusercontent.com/analogdevicesinc/iio-oscilloscope/"
    "main/filters/adrv9009/"
    "Tx_BW100_IR122p88_Rx_BW100_OR122p88_ORx_BW100_OR122p88_DC245p76.txt"
)


def push_talise_profile(shell, tmp_path: Path) -> bool:
    """Push a Talise filter profile to ``adrv9009-phy.profile_config``.

    On ZC706 + ADRV9009 the default post-boot Talise state leaves the
    buffered RX path inert.  Pushing any DC-245.76 MHz profile triggers
    a Talise re-init that brings the radio up to ``radio_on``, after
    which DMA capture works.

    Returns ``True`` if a profile was applied, ``False`` if the sysfs
    ``profile_config`` node could not be located (e.g. driver build
    without debugfs support).
    """
    profile_sysfs = shell_out(
        shell,
        "find /sys/kernel/debug/iio /sys/bus/iio/devices "
        "-name profile_config 2>/dev/null | head -1",
    ).strip()
    if not profile_sysfs:
        profile_sysfs = shell_out(
            shell,
            "find /sys -name profile_config 2>/dev/null | head -1",
        ).strip()
    if not profile_sysfs:
        return False

    cache_dir = tmp_path / "talise_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / "talise_default.txt"
    if cached.exists() and cached.stat().st_size > 0:
        body = cached.read_text()
    else:
        with urllib.request.urlopen(_TALISE_PROFILE_URL, timeout=30) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
        cached.write_text(body)
    if not body.lstrip().startswith("<profile "):
        raise AssertionError(
            "Talise profile fetch returned non-XML content"
            f" (first 80 chars: {body[:80]!r})"
        )

    b64 = base64.b64encode(body.encode()).decode()
    shell_out(shell, f"printf '%s' '{b64}' | base64 -d > /tmp/talise.txt")
    size_on_target = shell_out(shell, "stat -c%s /tmp/talise.txt").strip()
    assert size_on_target == str(len(body.encode())), (
        f"Talise profile partial push: target has {size_on_target},"
        f" expected {len(body.encode())}"
    )
    shell_out(shell, f"cat /tmp/talise.txt > {profile_sysfs}")
    # Talise re-init re-runs the JESD bring-up sequence; give the FSM
    # time to relock both links before any sysfs check.
    time.sleep(3.0)

    # Profile push leaves the radio in ``calibrated`` (ENSM state 6) on
    # ZC706 builds — we need ``radio_on`` (state 7) before the buffered
    # RX path will deliver samples through DMA.
    phy_dir = profile_sysfs.rsplit("/", 1)[0]
    shell_out(shell, f"echo radio_on > {phy_dir}/ensm_mode")
    time.sleep(1.0)
    return True


# ---------------------------------------------------------------------------
# RX TPL disambiguation (ADRV9009 family)
# ---------------------------------------------------------------------------

_ADRV9009_RX_TPL_REG_HINT = "44a00000"
_ADRV9009_TPL_NAME = "ad_ip_jesd204_tpl_adc"


def resolve_adrv9009_rx_tpl(ctx) -> tuple[str, ...]:
    """Pick the RX TPL device when multiple TPLs share the same IIO name.

    Both the RX TPL (``...@44a00000``) and the OBS TPL (``...@44a08000``)
    probe to libiio with the same ``ad_ip_jesd204_tpl_adc`` name —
    ``ctx.find_device`` returns whichever probed first (typically OBS),
    but Talise's ``radio_on`` only streams framer-A (RX); a refill on
    OBS returns all zeros even though its DMA fires.  Prefer the RX TPL
    by reg address; fall back to the higher-numbered duplicate (cf_axi_adc
    binds the RX TPL after ``ad_adc`` binds OBS, so the RX iio:device has
    the larger numeric id).
    """
    rx_tpl_dev = None
    for d in ctx.devices:
        if d.name != _ADRV9009_TPL_NAME:
            continue
        try:
            of_node = d.attrs["of_node"].value if "of_node" in d.attrs else ""
        except Exception:  # noqa: BLE001 — attr read may raise on some builds
            of_node = ""
        if _ADRV9009_RX_TPL_REG_HINT in of_node:
            rx_tpl_dev = d
            break

    if rx_tpl_dev is None:
        candidates = [d for d in ctx.devices if d.name == _ADRV9009_TPL_NAME]
        if candidates:
            rx_tpl_dev = max(
                candidates, key=lambda d: int(d.id.rsplit(":device", 1)[1])
            )

    if rx_tpl_dev is not None:
        return (rx_tpl_dev.id,)

    return (
        "axi-adrv9009-rx-hpc",
        "axi-adrv9009-rx-obs-hpc",
        _ADRV9009_TPL_NAME,
    )
