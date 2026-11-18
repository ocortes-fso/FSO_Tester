#!/usr/bin/env python3
"""
esc_arm.py - OPTIONAL power / arm / throttle control for an ESC telemetry run.

WHAT THIS IS, AND WHY IT IS OPTIONAL
------------------------------------
The rest of ESC_Serial is a pure listener. This module is the one piece that
can touch the hardware, and it exists so a telemetry capture can be run
end-to-end by one person: power the arm, arm the ESC, hold a throttle, log, and
power down - instead of needing someone else to drive the throttle while you
watch the numbers.

It does NOT reimplement any of that. Every call goes to the test box's own
subcodes, which already have the ordering, the clamps and the guards right:

    Precharge.INITIALIZE_SYSTEM()          claim the gpiochip, FET + precharge off
    Precharge.CLOSE_FET()                  (named "close" = de-energised)
    Hobbywing_Prop_Test.session_power_up() close the FETs, verify the bus came
                                           up, arm the over-current /
                                           under-voltage guards, start the
                                           INA228 sampler and its CSV
    Manual_PWM_Test.arm()                  hold 1000 us so the ESC will arm,
                                           then settle at SLIDER_MIN_US
    Manual_PWM_Test.set_channel(ch, us)    clamped to [1080, 1400] us
    Manual_PWM_Test.disarm()               frames off, ESC beeps 1/s
    Hobbywing_Prop_Test.session_power_off()
    Precharge.CLOSE_SYSTEM()               release the gpiochip

So the throttle ceiling, the arming sequence and the guards are whatever
Manual_PWM_Test and Hobbywing_Prop_Test say they are. Nothing here can exceed
them, and nothing here needs updating when they change.

ONLY ONE OWNER OF THE ARM AT A TIME
-----------------------------------
This is the hazard, and it is checked rather than documented-and-hoped. The
FET and the two throttle lines can only be owned by one process: if MasterUI
has the arm powered on its Prop TEST V2 or Cv2_A06 page, this must not also be
driving it, or two processes are commanding one FET with neither aware of the
other.

Precharge only holds the gpiochip BETWEEN power-on and power-off, so a test box
sitting on its menu is not holding anything and this can take ownership
cleanly. power_up() verifies that by claiming the FET line explicitly and
refusing if it cannot - see the comment there for why the claim has to be
re-done rather than trusted to INITIALIZE_SYSTEM.

IMPORTS ARE LAZY, ON PURPOSE
----------------------------
Subcodes is imported inside the functions, not at module scope, so that:
  * the read-only tools (esc_monitor, esc_sniff, esc_gui without --control)
    keep their zero-coupling guarantee and do not need lgpio at all;
  * the whole package still runs on a laptop against a USB-TTL adapter, where
    lgpio and smbus2 do not exist.
"""

from __future__ import annotations

import os
import sys
import threading

# The repo root, so `from Subcodes import ...` resolves the same way it does
# for GUI/MasterUI.py.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ArmError(RuntimeError):
    """Control is not available, or was refused. The message is operator-facing."""


_lock = threading.Lock()
_owned = False          # True once we have taken the gpiochip and powered up


def _subcodes():
    """Import the test box modules on first use. Raises ArmError if impossible."""
    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)
    try:
        import lgpio
        from Subcodes import Hobbywing_Prop_Test, Manual_PWM_Test, Precharge
    except ImportError as e:
        raise ArmError(
            f"arm control needs the test box libraries ({e}). Run this on the "
            f"Pi, or use the monitor read-only without --control."
        ) from e
    return lgpio, Precharge, Hobbywing_Prop_Test, Manual_PWM_Test


def available():
    """True if arm control could be used here. Does not claim anything."""
    try:
        _subcodes()
        return True
    except ArmError:
        return False


def owned():
    return _owned


# ---------------------------------------------------------------------------
# Power
# ---------------------------------------------------------------------------

def power_up(quiet=True):
    """
    Take ownership of the arm and bring the bus up. Blocking, seconds.

    Raises ArmError with an operator-facing message if the arm is already owned
    (the test box has it powered) or if the bus does not come up.

    No frames are transmitted here - same as the test box's own power-on, the
    ESC should be sitting there beeping once a second when this returns. Arming
    is a separate, deliberate step.
    """
    global _owned
    with _lock:
        if _owned:
            raise ArmError("already powered by this process")

        lgpio, Precharge, Prop, _Manual = _subcodes()

        Precharge.INITIALIZE_SYSTEM()

        # Verify we actually OWN the FET line, and do not trust
        # INITIALIZE_SYSTEM to have told us: it wraps its claims in bare
        # `except: pass` (so that re-initialising is harmless), which also
        # swallows the "another process has this line" error we care about.
        # Claiming it again here is the only way to see that error.
        try:
            lgpio.gpio_claim_output(Precharge.h, Precharge.FET_CTL, level=0)
        except lgpio.error as e:
            Precharge.CLOSE_SYSTEM()
            raise ArmError(
                "the arm is already owned by another process - almost "
                "certainly the test box has it powered. Press POWER OFF on its "
                f"Prop TEST V2 / Cv2_A06 page first. ({e})"
            ) from e

        Precharge.CLOSE_FET()

        try:
            # Does the bus check and arms the over-current / under-voltage
            # guards, and starts the INA228 sampler plus its own CSV in Logs/.
            # That trace is worth having next to the ESC's own numbers: two
            # independent measurements of the same current.
            Prop.session_power_up(guards_enabled=True, quiet=quiet)
        except Exception as e:
            # session_power_up leaves the FET open on failure; still release
            # the chip so the test box can have it back.
            Precharge.CLOSE_SYSTEM()
            raise ArmError(str(e)) from e

        _owned = True


def power_off():
    """
    Frames off, FET off, guards and sampler stopped, gpiochip released.

    Safe to call when nothing is powered, and safe to call twice - which is why
    every teardown path can just call it.
    """
    global _owned
    with _lock:
        if not _owned:
            return
        try:
            _lgpio, Precharge, Prop, Manual = _subcodes()
        except ArmError:
            _owned = False
            return
        try:
            Manual.release()                # abort, frames off, both channels
            Prop.session_power_off()
            Prop.session_stop_monitor()     # closes the INA228 CSV too
        finally:
            Precharge.CLOSE_SYSTEM()
            _owned = False


def emergency_stop(reason="operator pressed STOP"):
    """
    The hard stop: hand straight to the test box's own emergency path.

    Not a tidier power_off(): session_emergency_stop() is the sequence the rig
    already trusts for this, including killing the LED and keeping the fault
    log. Reusing it means there is one emergency stop on this hardware, not
    two with slightly different orderings.
    """
    global _owned
    with _lock:
        if not _owned:
            return
        try:
            _lgpio, Precharge, Prop, Manual = _subcodes()
        except ArmError:
            _owned = False
            return
        try:
            Manual.abort()
            Manual.all_off()
            Prop.session_emergency_stop()
        finally:
            Precharge.CLOSE_SYSTEM()
            _owned = False
        print(f"[ESC ARM] EMERGENCY STOP: {reason}")


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------

def arm():
    """
    Run the ESC arming hold. BLOCKING for ~2 s - call from a worker thread.

    Returns True if it completed. Both channels are armed together, which is
    Manual_PWM_Test's behaviour and the right one here too: the ESC you are not
    reading keeps live frames at its zero point instead of losing signal.

    NOTHING SPINS. The hold is at US_ARM (1000 us) and it settles at
    SLIDER_MIN_US (1080 us), both below the ESC's 0% point of 1100 us. That is
    what makes a telemetry capture possible before you are ready to turn a
    motor.
    """
    if not _owned:
        raise ArmError("not powered - power_up() first")
    _lgpio, _Precharge, _Prop, Manual = _subcodes()
    return Manual.arm()


def disarm():
    """Frames off on both channels. The ESC goes back to beeping once a second."""
    if not _owned:
        return
    _lgpio, _Precharge, _Prop, Manual = _subcodes()
    Manual.disarm()


def is_armed():
    if not _owned:
        return False
    try:
        _lgpio, _Precharge, _Prop, Manual = _subcodes()
    except ArmError:
        return False
    return Manual.is_armed()


def set_us(channel, us):
    """
    Command one channel. Returns what was actually transmitted.

    Clamped by Manual_PWM_Test to [SLIDER_MIN_US, US_MAX_ALLOWED] - 1080 to
    1400 us, about 40% throttle at the top. This module deliberately has no
    clamp of its own: one ceiling, defined in one place.
    """
    if not _owned:
        raise ArmError("not powered - power_up() first")
    _lgpio, _Precharge, _Prop, Manual = _subcodes()
    return Manual.set_channel(channel, us)


def limits():
    """(min_us, max_us, arm_us, zero_pct_us) from Manual_PWM_Test."""
    _lgpio, _Precharge, _Prop, Manual = _subcodes()
    return (Manual.SLIDER_MIN_US, Manual.US_MAX_ALLOWED, Manual.US_ARM, 1100)


def channels():
    _lgpio, _Precharge, _Prop, Manual = _subcodes()
    return sorted(Manual.CHANNELS)


# ---------------------------------------------------------------------------
# The independent measurement
# ---------------------------------------------------------------------------

def shunt_state():
    """
    The INA228 reading: {'volts', 'amps', 'temp_c', 'abort_reason', ...}.

    This is the cross-check that makes the whole exercise verifiable. The ESC
    reports its own current over the telemetry wire; the shunt measures the
    same current independently. Two numbers that agree are two numbers you can
    trust, and their ratio is exactly what calibrates the ESC's current scale.

    Returns {} when nothing is powered. Never does I2C itself - the sampler
    thread owns the bus, this just copies its state dict.
    """
    if not _owned:
        return {}
    try:
        _lgpio, _Precharge, Prop, _Manual = _subcodes()
    except ArmError:
        return {}
    return Prop.get_state()


def guard_tripped():
    """The abort reason if a guard fired, else None."""
    return (shunt_state() or {}).get("abort_reason")
