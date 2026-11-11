"""
#####*****CHANGES*****##### NEW FILE
Manual PWM test for the Cv2_A06 arm - "drive the ESCs by hand".

WHAT THIS IS FOR
----------------
Hobbywing_Prop_Test.py runs a fixed, scripted sequence: you press a button and
it walks through a table of throttle steps and holds. That is the right tool for
a repeatable acceptance test, and the wrong tool for the two things this page
needs:

  1. "which way does this motor turn?"  -> one short, low nudge, on one channel
  2. "let me creep the throttle up by hand and watch/listen"

So this module does the opposite of the scripted one: no sequence table, no
phases, no pass/fail. Just two channels you can command to any value inside a
deliberately low ceiling, plus one canned 3-second nudge per channel.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
  * No power control. Closing the FET and checking the bus came up stays in
    Hobbywing_Prop_Test.session_power_up() - one implementation, one place to
    get the ordering right.
  * No I2C. Hobbywing_Prop_Test's Telemetry thread is the only thing on the
    whole GUI that reads the INA228, because Batt_monitor shares a single
    SMBus object and two readers would race. The GUI reads voltage/current
    from Hobbywing_Prop_Test.get_state(); this module never touches the bus.
  * No guards. The over-current / under-voltage trip also lives on that
    telemetry thread and is already armed by session_power_up(), so it protects
    this page too without any work here.

WHY NOT JUST REUSE SoftServoPWM?
--------------------------------
Two reasons, both about things this page needs and the scripted test does not:

  * SoftServoPWM.stop() latches `disabled = True` on purpose, so an emergency
    stop can never be followed by another throttle command while a worker
    thread unwinds. Correct there - but it makes stop/start cycling impossible,
    and this page is nothing but stop/start cycling.
  * Its clamp floor is 1000 us, so it cannot express "no frames at all". Here
    the resting state of a channel has to be genuinely 0 us (no waveform), both
    because that is what the operator asked for and because a beeping ESC is an
    unmistakable "this channel is not armed".

So the tx_servo() handling is duplicated here, with a different clamp and no
latch. It is about fifteen lines; sharing it would have meant bending the
scripted test's safety model to suit a manual one.
"""

import threading
import time

import lgpio

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import Precharge


# ---------------------------------------------------------------------------
# Configuration - the numbers worth changing are all here
# ---------------------------------------------------------------------------

# Same two lines the scripted test uses. Imported as plain ints rather than
# from Hobbywing_Prop_Test so this module has no dependency on it at all:
# nothing here needs the scripted test to be loaded, and keeping the import
# out avoids a circular one if that module ever wants to call into this.
PWM_TOP = 7          # GPIO7  -> TOP ESC throttle signal
PWM_BOT = 5          # GPIO5  -> BOT ESC throttle signal

# GPIO5 and GPIO7 are not on the Pi 5's hardware PWM block (that is 12/13/18/19),
# so these are software-generated servo frames via lgpio.tx_servo(). Same
# frequency the scripted test uses - keep the two in step, an ESC that was
# calibrated at one frame rate should not be driven at another.
PWM_FREQ_HZ = 400

# --- the slider band ------------------------------------------------------
#
# SLIDER_MIN_US is the slider's resting position AND means "frames off".
# Mapping the bottom of the travel to no-waveform rather than to 1000 us is
# deliberate:
#
#   * it is what the operator asked for - the reset position is 0 us out
#   * 1000 us is the ESC's disarm value, so it would not spin there anyway;
#     the only difference between "1000 us frames" and "no frames" is the
#     once-per-second beep, and that beep is a useful, audible "not armed"
#   * it means the whole slider travel is the useful band. A 0..1400 slider
#     would waste 71% of its length on throttle values below the ESC's own
#     floor, leaving the part that matters squeezed into the last few pixels
#     of a touchscreen.
#
# SLIDER_MAX_US is the manual ceiling. THIS IS THE ONE TO CHANGE if you want
# more or less headroom. 1400 us is roughly 40% throttle on this ESC
# (1100 = 0%, 1310 = 25%, 1520 = 50%), which is enough to see direction,
# hear a bearing and watch the current draw, and low enough that a slip of
# the finger on a bench with props fitted is not an event.
SLIDER_MIN_US = 1000
SLIDER_MAX_US = 1400

# Hard ceiling enforced in code, independent of whatever the widget allows.
# Belt and braces: the clamp is what actually protects the hardware, the slider
# range is just what the operator can reach. Raise SLIDER_MAX_US and this
# follows; it exists so a stray set_channel() call from anywhere cannot exceed
# the band either.
US_MAX_ALLOWED = SLIDER_MAX_US

US_OFF = 0           # tx_servo() pulse width 0 = switch this waveform off

# --- the canned nudge -----------------------------------------------------
# One channel, low throttle, a few seconds: long enough to watch the prop and
# call the direction, short enough that nothing gets hot. 1200 us is just above
# the ESC's 0% point (1100 us), so it turns slowly.
SPIN_US = 1200
SPIN_HOLD_S = 3.0

CHANNELS = {"top": PWM_TOP, "bot": PWM_BOT}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
# Its own stop Event, NOT Hobbywing_Prop_Test's. That module has a single
# module-level stop event which the GUI has already handed to the Prop TEST V2
# page via register_stop_event(); registering another one here would silently
# break cancelling over there. The two pages abort independently.
_stop = threading.Event()

_lock = threading.Lock()
_state = {
    "top_us": None,     # what is actually going out, None = no frames
    "bot_us": None,
    "busy": None,       # which channel a timed spin is running on, if any
}


def register_stop_event(event):
    """Let the GUI supply its own Event, the way the other subcodes do."""
    global _stop
    _stop = event


def abort():
    """Cut a running timed spin short. Returns immediately; the worker unwinds."""
    _stop.set()


def clear_abort():
    _stop.clear()


def stop_requested():
    return _stop.is_set()


def state():
    """Snapshot for the GUI labels. No I2C, no blocking - safe on the Tk thread."""
    with _lock:
        return dict(_state)


def _set_state(**kw):
    with _lock:
        _state.update(kw)


def channel_us(channel):
    """What `channel` is currently transmitting, or None if frames are off."""
    with _lock:
        return _state[f"{channel}_us"]


def busy_channel():
    with _lock:
        return _state["busy"]


# ---------------------------------------------------------------------------
# PWM
# ---------------------------------------------------------------------------

def _handle():
    """
    The live gpiochip handle, looked up fresh every call.

    Never cached. An emergency stop calls Precharge.CLOSE_SYSTEM(), which closes
    the chip and sets Precharge.h back to None - a cached handle would be stale
    from that moment on, and writing to a closed handle is exactly the failure
    this avoids.
    """
    return Precharge.h


def claim():
    """
    Claim both throttle lines as outputs, driven low (no pulses -> ESC beeps).

    Usually a no-op in practice: session_power_up() has already claimed these
    two pins on the same handle. Tolerating that is the point - an already-
    claimed line raises lgpio.error and there is nothing wrong with it.
    """
    h = _handle()
    if h is None:
        raise RuntimeError("GPIO not initialised - power on first")

    for pin in CHANNELS.values():
        try:
            lgpio.gpio_claim_output(h, pin, level=0)
        except lgpio.error:
            pass    # already ours


def _clamp(us):
    us = int(round(us))
    clamped = max(SLIDER_MIN_US, min(US_MAX_ALLOWED, us))
    if clamped != us:
        print(f"[MANUAL PWM] {us} us clamped to {clamped} us")
    return clamped


def set_channel(channel, us):
    """
    Command one channel. Returns the value actually transmitted, or None if the
    channel ended up off.

    Anything at or below SLIDER_MIN_US turns the frames off rather than sending
    a floor value - see the comment on SLIDER_MIN_US. That is what makes the
    bottom of the slider a real resting position instead of a quiet throttle.
    """
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")

    if us is None or us <= SLIDER_MIN_US:
        off(channel)
        return None

    h = _handle()
    if h is None:
        raise RuntimeError("GPIO not initialised - power on first")

    us = _clamp(us)
    try:
        lgpio.tx_servo(h, CHANNELS[channel], us, PWM_FREQ_HZ)
    except lgpio.error as e:
        # The handle can be closed under us by an emergency stop on the Tk
        # thread while a spin worker is still unwinding. The frames are already
        # gone by then, so there is nothing left to fail at - say so and carry
        # on rather than raising into the worker's teardown.
        print(f"[MANUAL PWM] tx_servo pin={CHANNELS[channel]}: {e}")
        _set_state(**{f"{channel}_us": None})
        return None

    _set_state(**{f"{channel}_us": us})
    return us


def off(channel):
    """Stop the frames on one channel and leave the line low. ESC goes back to beeping."""
    h = _handle()
    _set_state(**{f"{channel}_us": None})

    if h is None:
        return      # already torn down, nothing to switch off

    pin = CHANNELS[channel]
    try:
        lgpio.tx_servo(h, pin, US_OFF, PWM_FREQ_HZ)
        lgpio.gpio_write(h, pin, 0)
    except lgpio.error as e:
        print(f"[MANUAL PWM] off pin={pin}: {e}")


def all_off():
    """Both channels off. The safe state, and where every path here ends up."""
    for channel in CHANNELS:
        off(channel)


def release():
    """
    Hand the lines back to a known-safe state.

    Called when the page is left and before a normal power-off, so the rig is
    never left transmitting throttle by a navigation action.
    """
    abort()
    all_off()
    _set_state(busy=None)


# ---------------------------------------------------------------------------
# The canned nudge
# ---------------------------------------------------------------------------

def _interruptible_sleep(duration, slice_s=0.02):
    """
    sleep() that notices an abort, checked every slice_s.

    A local copy rather than Hobbywing_Prop_Test's, because that one watches
    that module's stop event and this page has its own - see the note on _stop.

    Returns True if the wait was cut short.
    """
    end = time.monotonic() + duration
    while True:
        if stop_requested():
            return True
        remaining = end - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(slice_s, remaining))


def spin(channel, us=SPIN_US, hold_s=SPIN_HOLD_S, on_tick=None):
    """
    Nudge one channel at `us` for `hold_s`, then switch its frames off.

    BLOCKING - call it from a worker thread, not from the Tk thread, or the
    window freezes for three seconds and the emergency stop with it.

    Only the named channel is touched. The other one is left exactly as it was,
    which is what makes "spin TOP and watch which way it goes" a one-motor
    test: the BOT ESC keeps beeping away, unarmed, throughout.

    `on_tick(remaining_s)` is called about 10x a second if given, for a
    countdown. It runs on the worker thread, so a GUI caller must marshal to
    the Tk thread itself rather than touching widgets in it.

    Returns True if the full hold elapsed, False if it was cut short - by the
    operator, or by the telemetry guards tripping.

    The try/finally is the whole safety story: no matter how this exits -
    normal end, abort, or an exception out of tx_servo - the channel's frames
    are switched off on the way out.
    """
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")

    clear_abort()
    _set_state(busy=channel)

    completed = False
    try:
        print(f"[MANUAL PWM] {channel.upper()} spin {us} us for {hold_s:.1f}s")
        set_channel(channel, us)

        # Tick in slices so the countdown updates and an abort is noticed
        # within ~100 ms, instead of one long blind sleep.
        end = time.monotonic() + hold_s
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                completed = True
                break
            if on_tick is not None:
                on_tick(remaining)
            if _interruptible_sleep(min(0.1, remaining)):
                print(f"[MANUAL PWM] {channel.upper()} spin aborted")
                break

    finally:
        off(channel)
        _set_state(busy=None)
        print(f"[MANUAL PWM] {channel.upper()} spin {'complete' if completed else 'stopped'}"
              f" - frames off")

    return completed


# ---------------------------------------------------------------------------
# Standalone use
# ---------------------------------------------------------------------------
# Lets the manual test be driven from a terminal with no GUI, which is how you
# check the wiring and the direction of rotation on a bench without the
# touchscreen attached:
#
#     python3 -m Subcodes.Manual_PWM_Test top
#     python3 -m Subcodes.Manual_PWM_Test bot 1250 5
#
# Power is still taken through Hobbywing_Prop_Test, so the bus check and the
# guards apply here exactly as they do on the page. The import is inside main()
# so the GUI never pays for it.

def main():
    import argparse

    from Subcodes import Hobbywing_Prop_Test

    ap = argparse.ArgumentParser(description="Manual PWM nudge on one channel")
    ap.add_argument("channel", choices=sorted(CHANNELS), help="which ESC")
    ap.add_argument("us", nargs="?", type=int, default=SPIN_US,
                    help=f"pulse width (default {SPIN_US}, max {US_MAX_ALLOWED})")
    ap.add_argument("hold", nargs="?", type=float, default=SPIN_HOLD_S,
                    help=f"seconds (default {SPIN_HOLD_S})")
    args = ap.parse_args()

    Precharge.INITIALIZE_SYSTEM()
    Precharge.CLOSE_FET()

    print(f"Powering up (bus must reach {Precharge.BUS_MIN_VOLTAGE:.0f} V)")
    Hobbywing_Prop_Test.session_power_up(guards_enabled=True, quiet=False)
    try:
        claim()
        spin(args.channel, us=args.us, hold_s=args.hold,
             on_tick=lambda r: print(f"  {r:4.1f}s left", end="\r"))
    finally:
        release()
        Hobbywing_Prop_Test.session_power_off()
        Hobbywing_Prop_Test.session_stop_monitor()
        Precharge.CLOSE_SYSTEM()


if __name__ == "__main__":
    main()
