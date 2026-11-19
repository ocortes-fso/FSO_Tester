#!/usr/bin/env python3
"""
esc_arm.py - OPTIONAL arm / throttle control for an ESC telemetry run.

BENCH WIRING THIS ASSUMES
-------------------------
    Battery ------------> ESC ------------> 3-phase motor
    ESC white (PWM in) -> GPIO7 (pin 26, "top")  or  GPIO5 (pin 29, "bot")
    ESC black (GND) ----> Pi GND (pin 25 / 30)
    ESC green (UART) ---> Pi 5 UART debug connector RX  (read by esc_monitor)

There is NO precharge FET, NO INA228 / I2C and NO bus-voltage check here: the
battery feeds the ESC directly, so the ESC is live as soon as it is plugged in.
The only thing this module touches is one gpiochip handle and the two throttle
lines, driven with lgpio software servo pulses (GPIO5/7 are not hardware-PWM
pins on the Pi 5).

The pulse widths, the arming hold and the slider band are the same numbers
Subcodes/Manual_PWM_Test.py uses, copied here rather than imported so this
module does not pull in Precharge. Keep them in step if those change.

ONE OWNER OF THE LINES AT A TIME
--------------------------------
power_up() claims GPIO5/GPIO7 and refuses if another process (e.g. MasterUI)
already holds them.

IMPORTS ARE LAZY
----------------
lgpio is imported on first use so the read-only tools still run on a laptop.
"""

from __future__ import annotations

import threading
import time

# --- same values as Subcodes/Manual_PWM_Test.py ---------------------------
GPIOCHIP = 4            # Pi 5 RP1 header chip, same as Precharge.CHIP
PWM_TOP = 7             # GPIO7, physical pin 26
PWM_BOT = 5             # GPIO5, physical pin 29
CHANNELS = {"top": PWM_TOP, "bot": PWM_BOT}
PWM_FREQ_HZ = 400

US_ARM = 1000           # held while the ESC arms
ARM_HOLD_S = 2.0
SLIDER_MIN_US = 1080    # armed resting value, below the 1100 us 0% point
SLIDER_MAX_US = 1400    # ~40% throttle - the ceiling
US_MAX_ALLOWED = SLIDER_MAX_US
ZERO_PCT_US = 1100
US_OFF = 0              # tx_servo width 0 = waveform off


class ArmError(RuntimeError):
    """Control is not available, or was refused. The message is operator-facing."""


_lock = threading.Lock()
_stop = threading.Event()
_h = None               # gpiochip handle while we own the lines
_armed = False
_us = {name: None for name in CHANNELS}


def _lgpio():
    try:
        import lgpio
    except ImportError as e:
        raise ArmError(
            f"PWM control needs lgpio ({e}). Run this on the Pi, or use the "
            f"monitor read-only without --control.") from e
    return lgpio


def available():
    """True if PWM control could be used here. Claims nothing."""
    try:
        _lgpio()
        return True
    except ArmError:
        return False


def owned():
    return _h is not None


# ---------------------------------------------------------------------------
# Claim / release the throttle lines
# ---------------------------------------------------------------------------

def power_up(quiet=True):
    """
    Open the gpiochip and claim GPIO5/GPIO7 as outputs, driven low.

    No pulses yet - the ESC keeps beeping until arm(). Raises ArmError if the
    lines are already held by another process.
    """
    global _h, _armed
    with _lock:
        if _h is not None:
            raise ArmError("PWM lines already claimed by this process")
        lgpio = _lgpio()
        try:
            h = lgpio.gpiochip_open(GPIOCHIP)
        except lgpio.error as e:
            raise ArmError(f"cannot open gpiochip{GPIOCHIP}: {e}") from e
        try:
            for pin in CHANNELS.values():
                lgpio.gpio_claim_output(h, pin, 0)
        except lgpio.error as e:
            lgpio.gpiochip_close(h)
            raise ArmError(
                "GPIO5/GPIO7 are held by another process - close the test box "
                f"page that is driving them first. ({e})") from e
        _h = h
        _armed = False
        for name in _us:
            _us[name] = None
        if not quiet:
            print(f"[ESC ARM] claimed GPIO{PWM_TOP}/GPIO{PWM_BOT}, no pulses")


def _off_all(lgpio):
    """Pulses off, lines low. Caller holds _lock and _h is valid."""
    global _armed
    for name, pin in CHANNELS.items():
        try:
            lgpio.tx_servo(_h, pin, US_OFF, PWM_FREQ_HZ)
            lgpio.gpio_write(_h, pin, 0)
        except lgpio.error as e:
            print(f"[ESC ARM] off GPIO{pin}: {e}")
        _us[name] = None
    _armed = False


def power_off():
    """Pulses off, lines released, chip closed. Safe to call any time, twice."""
    global _h
    _stop.set()
    with _lock:
        if _h is None:
            return
        lgpio = _lgpio()
        try:
            _off_all(lgpio)
            for pin in CHANNELS.values():
                try:
                    lgpio.gpio_free(_h, pin)
                except lgpio.error:
                    pass
        finally:
            try:
                lgpio.gpiochip_close(_h)
            except lgpio.error:
                pass
            _h = None


def emergency_stop(reason="operator pressed STOP"):
    """Cut the throttle pulses immediately and release the lines."""
    power_off()
    print(f"[ESC ARM] EMERGENCY STOP: {reason} - PWM off. "
          f"Unplug the battery to remove power from the ESC.")


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------

def _emit(lgpio, name, us):
    lgpio.tx_servo(_h, CHANNELS[name], int(us), PWM_FREQ_HZ)
    _us[name] = int(us)


def arm():
    """
    Hold US_ARM on both channels for ARM_HOLD_S, then settle at SLIDER_MIN_US.
    BLOCKING ~2 s - call from a worker thread. Nothing spins.

    Returns True if the hold completed, False if aborted.
    """
    global _armed
    lgpio = _lgpio()
    _stop.clear()
    with _lock:
        if _h is None:
            raise ArmError("PWM not enabled - power_up() first")
        for name in CHANNELS:
            _emit(lgpio, name, US_ARM)
    print(f"[ESC ARM] arming at {US_ARM} us for {ARM_HOLD_S:.1f}s")

    end = time.monotonic() + ARM_HOLD_S
    while time.monotonic() < end:
        if _stop.wait(0.02):
            with _lock:
                if _h is not None:
                    _off_all(lgpio)
            return False

    with _lock:
        if _h is None:
            return False
        for name in CHANNELS:
            _emit(lgpio, name, SLIDER_MIN_US)
        _armed = True
    print(f"[ESC ARM] armed - idling at {SLIDER_MIN_US} us")
    return True


def disarm():
    """Pulses off on both channels. The ESC goes back to beeping."""
    _stop.set()
    with _lock:
        if _h is None:
            return
        _off_all(_lgpio())


def is_armed():
    return _h is not None and _armed


def set_us(channel, us):
    """
    Command one channel, clamped to [SLIDER_MIN_US, US_MAX_ALLOWED].
    Returns the value actually transmitted.
    """
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    lgpio = _lgpio()
    with _lock:
        if _h is None or not _armed:
            raise ArmError("not armed - arm() first")
        us = SLIDER_MIN_US if us is None else int(round(us))
        us = max(SLIDER_MIN_US, min(US_MAX_ALLOWED, us))
        if _us[channel] != us:
            _emit(lgpio, channel, us)
        return us


def limits():
    """(min_us, max_us, arm_us, zero_pct_us)."""
    return (SLIDER_MIN_US, US_MAX_ALLOWED, US_ARM, ZERO_PCT_US)


def channels():
    return sorted(CHANNELS)


# ---------------------------------------------------------------------------
# No shunt on this bench - kept so callers need no special case.
# ---------------------------------------------------------------------------

def shunt_state():
    """Always {}: battery is wired straight to the ESC, there is no INA228."""
    return {}


def guard_tripped():
    return None
