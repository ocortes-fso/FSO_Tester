#!/usr/bin/env python3
"""
esc_arm.py - OPTIONAL power / arm / throttle control for an ESC telemetry run.

BENCH WIRING THIS ASSUMES
-------------------------
    Battery --> FETs (FET_CTL, GPIO0) --> INA228 --> ESC --> 3-phase motor
    ESC white (PWM in) -> GPIO7 (pin 26, "top")  or  GPIO5 (pin 29, "bot")
    ESC black (GND) ----> Pi GND (pin 25 / 30)
    ESC green (UART) ---> Pi 5 UART debug connector RX  (read by esc_monitor)

PRE-ARM CHECK - SAME ORDER AS Subcodes/Precharge.py
---------------------------------------------------
power_up() follows the sequence Precharge.py lays out, calling Precharge's own
functions rather than copying them, so the order and the threshold have one
definition:

    1. Precharge.INITIALIZE_SYSTEM()   claim gpiochip; PRECHARGE held at 1
                                       (inactive), FET off
    2. claim GPIO5/GPIO7 low           no throttle pulses while the bus rises
    3. Precharge.START_PRECHARGE()     no-op while precharge is DISABLED
                                       (hardware fault) - kept so the redesign
                                       only has to uncomment Precharge.py
    4. Precharge.OPEN_FET()            FETs conduct - ESC powered
    5. Precharge.TURN_OFF_PRECHARGE()  PRECHARGE back to inactive
    6. sleep Precharge.BUS_SETTLE_S    let the bus come up
    7. read the INA228 (median)        the monitor is on the FET OUTPUT, so
                                       there is nothing to read before step 4
    8. Precharge.classify_bus_voltage  must reach Precharge.BUS_MIN_VOLTAGE;
                                       if not: CLOSE_FET, TURN_OFF_PRECHARGE,
                                       release everything, refuse

This catches a bus that fails to come up (flat pack, blown fuse, bad FET
wiring). It does NOT limit inrush into the ESC capacitance - that protection
returns with the redesigned precharge board (see Precharge.py).

The gpiochip handle is Precharge.h, shared with the throttle lines, exactly as
the Subcodes do it: a second handle on the same chip would fight over claims.

Teardown (power_off / emergency_stop): pulses off, throttle lines freed,
CLOSE_FET, TURN_OFF_PRECHARGE, CLOSE_SYSTEM.

ONE OWNER OF THE LINES AT A TIME
--------------------------------
power_up() claims FET_CTL and GPIO5/GPIO7 and refuses if another process (e.g.
MasterUI) already holds them.

IMPORTS ARE LAZY
----------------
lgpio, Precharge and Batt_monitor are imported on first use so the read-only
tools still run on a laptop.
"""

from __future__ import annotations

import os
import sys
import threading
import time

# Repo root, so `from Subcodes import ...` resolves as it does for MasterUI.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- same values as Subcodes/Manual_PWM_Test.py ---------------------------
PWM_TOP = 7             # GPIO7, physical pin 26
PWM_BOT = 5             # GPIO5, physical pin 29
CHANNELS = {"top": PWM_TOP, "bot": PWM_BOT}
PWM_FREQ_HZ = 400

US_ARM = 1000           # held while the ESC arms
ARM_HOLD_S = 2.0
SLIDER_MIN_US = 1080    # armed resting value, below the 1100 us 0% point
SLIDER_MAX_US = 1400    # ~40% throttle - the manual slider's ceiling
ZERO_PCT_US = 1100
US_OFF = 0              # tx_servo width 0 = waveform off

# --- sweep ----------------------------------------------------------------
# 1000 us (0 rpm) -> SWEEP_END_US (~1500 rpm at 1690) over ~5 s, then the
# signal is cut so the spin-down can be timed. SWEEP_END_US is the value to
# change to sweep to a different target. 1690 us is
# Hobbywing_Prop_Test.US_70, that module's hard clamp, and is the absolute
# ceiling here too: nothing in this module may command more.
SWEEP_START_US = US_ARM
SWEEP_END_US = 1690
SWEEP_DURATION_S = 5.0
SWEEP_STEP_S = 0.02     # 50 Hz of updates, well inside the 400 Hz frame rate
US_MAX_ALLOWED = SWEEP_END_US

# --- bus check (threshold and settle time live in Precharge.py) -----------
BUS_CHECK_SAMPLES = 5   # same as Hobbywing_Prop_Test
BUS_CHECK_INTERVAL_S = 0.05


class ArmError(RuntimeError):
    """Control is not available, or was refused. The message is operator-facing."""


_lock = threading.Lock()
_stop = threading.Event()
_owned = False          # True while we hold the chip, the FET and the lines
_armed = False
_us = {name: None for name in CHANNELS}


def _mods():
    """(lgpio, Precharge, Batt_monitor), imported on first use."""
    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)
    try:
        import lgpio
        from Subcodes import Batt_monitor, Precharge
    except ImportError as e:
        raise ArmError(
            f"PWM control needs lgpio, smbus2 and Subcodes/Precharge ({e}). "
            f"Run this on the Pi, or use the monitor read-only without "
            f"--control.") from e
    return lgpio, Precharge, Batt_monitor


def available():
    """True if PWM control could be used here. Claims nothing."""
    try:
        _mods()
        return True
    except ArmError:
        return False


def owned():
    return _owned


def _h():
    """Precharge.h, looked up fresh - CLOSE_SYSTEM() sets it back to None."""
    _lgpio, Precharge, _bm = _mods()
    return Precharge.h


# ---------------------------------------------------------------------------
# Pre-arm check / power
# ---------------------------------------------------------------------------

def read_bus_voltage(samples=BUS_CHECK_SAMPLES):
    """Median INA228 bus voltage over a few samples, or None if nothing read."""
    _lgpio, _Precharge, Batt_monitor = _mods()
    reads = []
    for _ in range(samples):
        v = Batt_monitor.read_battery_voltage()
        if v is not None:
            reads.append(v)
        time.sleep(BUS_CHECK_INTERVAL_S)
    if not reads:
        return None
    reads.sort()
    return reads[len(reads) // 2]


def _teardown(lgpio, Precharge):
    """Pulses off, lines freed, FET off, precharge off, chip closed."""
    global _owned, _armed
    h = Precharge.h
    if h is not None:
        for name, pin in CHANNELS.items():
            try:
                lgpio.tx_servo(h, pin, US_OFF, PWM_FREQ_HZ)
                lgpio.gpio_write(h, pin, 0)
            except lgpio.error as e:
                print(f"[ESC ARM] off GPIO{pin}: {e}")
            try:
                lgpio.gpio_free(h, pin)
            except lgpio.error:
                pass
    for name in _us:
        _us[name] = None
    _armed = False
    try:
        Precharge.CLOSE_FET()
        Precharge.TURN_OFF_PRECHARGE()
    except Exception as e:          # noqa: BLE001
        print(f"[ESC ARM] power down: {e}")
    finally:
        Precharge.CLOSE_SYSTEM()
        _owned = False


def power_up(quiet=True):
    """
    Pre-arm check in Precharge.py's order (see module docstring). Blocking,
    ~0.5 s.

    Returns the bus voltage. Raises ArmError with an operator-facing message
    if the lines are held elsewhere or the bus does not come up - in which
    case the FETs are off and everything is released again.

    No throttle pulses yet - the ESC keeps beeping until arm().
    """
    global _owned, _armed
    with _lock:
        if _owned:
            raise ArmError("already powered by this process")
        lgpio, Precharge, _bm = _mods()
        _stop.clear()

        # 1. chip claimed, PRECHARGE inactive, FET off
        try:
            Precharge.INITIALIZE_SYSTEM()
        except Exception as e:      # noqa: BLE001
            raise ArmError(f"GPIO init failed: {e}") from e
        h = Precharge.h

        # INITIALIZE_SYSTEM swallows claim errors with a bare except, which
        # also hides "another process owns this line". Re-claim to see it.
        try:
            lgpio.gpio_claim_output(h, Precharge.FET_CTL, level=0)
        except lgpio.error as e:
            Precharge.CLOSE_SYSTEM()
            raise ArmError(
                "the FET line is held by another process - almost certainly "
                "the test box has the arm powered. POWER OFF there first. "
                f"({e})") from e

        # 2. throttle lines low - no pulses while the bus comes up
        try:
            for pin in CHANNELS.values():
                lgpio.gpio_claim_output(h, pin, level=0)
        except lgpio.error as e:
            Precharge.CLOSE_SYSTEM()
            raise ArmError(
                "GPIO5/GPIO7 are held by another process - close the test box "
                f"page that is driving them first. ({e})") from e

        _owned = True
        _armed = False
        for name in _us:
            _us[name] = None

        try:
            # 3. no-op while precharge is disabled (hardware fault)
            Precharge.START_PRECHARGE()

            if _stop.is_set():
                raise ArmError("aborted before power up")

            # 4-5. FETs on, precharge back to inactive
            if not quiet:
                print("[ESC ARM] FETs on")
            Precharge.OPEN_FET()
            Precharge.TURN_OFF_PRECHARGE()

            # 6. let the bus come up before believing a reading
            time.sleep(Precharge.BUS_SETTLE_S)

            # 7-8. the monitor is on the FET output: check only now
            volts = read_bus_voltage()
            ok, message = Precharge.classify_bus_voltage(volts)
            if not ok:
                raise ArmError(f"bus check failed, FETs off again: {message}")
        except Exception as e:
            _teardown(lgpio, Precharge)
            if isinstance(e, ArmError):
                raise
            raise ArmError(f"power up failed: {e}") from e

        print(f"[ESC ARM] bus {message} - live, no pulses")
        return volts


def power_off():
    """Pulses off, FET off, lines released, chip closed. Safe any time, twice."""
    _stop.set()
    with _lock:
        if not _owned:
            return
        lgpio, Precharge, _bm = _mods()
        _teardown(lgpio, Precharge)


def emergency_stop(reason="operator pressed STOP"):
    """Cut the throttle pulses and the FET immediately."""
    power_off()
    print(f"[ESC ARM] EMERGENCY STOP: {reason} - PWM off, FETs off.")


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------

def _emit(lgpio, name, us):
    lgpio.tx_servo(_h(), CHANNELS[name], int(us), PWM_FREQ_HZ)
    _us[name] = int(us)


def _off_pulses(lgpio):
    """Pulses off, lines low, still owned. Caller holds _lock."""
    global _armed
    h = _h()
    for name, pin in CHANNELS.items():
        try:
            lgpio.tx_servo(h, pin, US_OFF, PWM_FREQ_HZ)
            lgpio.gpio_write(h, pin, 0)
        except lgpio.error as e:
            print(f"[ESC ARM] off GPIO{pin}: {e}")
        _us[name] = None
    _armed = False


def arm():
    """
    Hold US_ARM on both channels for ARM_HOLD_S, then settle at SLIDER_MIN_US.
    BLOCKING ~2 s - call from a worker thread. Nothing spins.

    Returns True if the hold completed, False if aborted.
    """
    global _armed
    lgpio, _P, _bm = _mods()
    _stop.clear()
    with _lock:
        if not _owned:
            raise ArmError("not powered - power_up() first")
        for name in CHANNELS:
            _emit(lgpio, name, US_ARM)
    print(f"[ESC ARM] arming at {US_ARM} us for {ARM_HOLD_S:.1f}s")

    end = time.monotonic() + ARM_HOLD_S
    while time.monotonic() < end:
        if _stop.wait(0.02):
            with _lock:
                if _owned:
                    _off_pulses(lgpio)
            return False

    with _lock:
        if not _owned:
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
        if not _owned:
            return
        _off_pulses(_mods()[0])


def is_armed():
    return _owned and _armed


def set_us(channel, us):
    """
    Command one channel, clamped to [US_ARM, US_MAX_ALLOWED].
    Returns the value actually transmitted.
    """
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    lgpio = _mods()[0]
    with _lock:
        if not _owned or not _armed:
            raise ArmError("not armed - arm() first")
        us = SLIDER_MIN_US if us is None else int(round(us))
        us = max(US_ARM, min(US_MAX_ALLOWED, us))
        if _us[channel] != us:
            _emit(lgpio, channel, us)
        return us


def sweep(channel, start_us=SWEEP_START_US, end_us=SWEEP_END_US,
          duration_s=SWEEP_DURATION_S, on_step=None):
    """
    Linear ramp start_us -> end_us over duration_s on one channel, then CUT
    THE SIGNAL (pulses off on both channels) to simulate the motors being
    switched off, so the coast-down can be timed from the telemetry.
    BLOCKING - call from a worker thread.

    The ESC is disarmed afterwards (no pulses) and must be re-armed before
    the next run. The FETs stay on, so telemetry keeps streaming through the
    spin-down.

    on_step(us) is called with each value actually transmitted, and with 0 at
    the cut. Aborted by disarm(), power_off() or emergency_stop() (they set
    _stop).

    Returns the time.monotonic() of the signal cut - the same clock as
    EscReader's t_mono - or None if the sweep was aborted.
    """
    if not is_armed():
        raise ArmError("not armed - arm() first")
    lgpio = _mods()[0]
    _stop.clear()
    print(f"[ESC ARM] sweep {channel}: {start_us} -> {end_us} us "
          f"over {duration_s:.1f}s, then signal off")
    t0 = time.monotonic()
    t_cut = None
    try:
        while True:
            frac = min(1.0, (time.monotonic() - t0) / duration_s)
            try:
                sent = set_us(channel, start_us + (end_us - start_us) * frac)
            except ArmError:
                if _stop.is_set():      # E-STOP / disarm got there first
                    return None
                raise
            if on_step:
                on_step(sent)
            if frac >= 1.0:
                break
            if _stop.wait(SWEEP_STEP_S):
                return None
    finally:
        # Completed or not, finish with no signal at all - never leave the
        # motor sitting at the top of the ramp.
        with _lock:
            if _owned:
                _off_pulses(lgpio)
                t_cut = time.monotonic()
    if on_step and t_cut is not None:
        on_step(0)
    print(f"[ESC ARM] sweep complete - signal OFF at {end_us} us, "
          f"timing spin-down")
    return t_cut


def limits():
    """(min_us, max_us, arm_us, zero_pct_us) for the manual slider."""
    return (SLIDER_MIN_US, SLIDER_MAX_US, US_ARM, ZERO_PCT_US)


def sweep_limits():
    """(start_us, end_us, duration_s)."""
    return (SWEEP_START_US, SWEEP_END_US, SWEEP_DURATION_S)


def channels():
    return sorted(CHANNELS)


# ---------------------------------------------------------------------------
# No shunt guard on this bench - kept so callers need no special case.
# ---------------------------------------------------------------------------

def shunt_state():
    """Always {}: no INA228 sampler / guards run here (bus check only)."""
    return {}


def guard_tripped():
    return None
