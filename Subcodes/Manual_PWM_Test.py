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
# --- ARMING, and why the resting value is NOT 0 us ------------------------
#
# This was wrong in the first version and it is worth writing down, because
# both bugs it caused looked like different problems.
#
# An ESC will not arm if the first throttle signal it ever sees is above its
# zero point. It emits a fast error beep and refuses. The first version jumped
# straight from "no frames at all" to 1200 us, so the first press of a Spin
# button always got the fast beep and never turned the motor; by the second
# press the ESC had been through its startup and behaved. That is exactly the
# sequence the scripted test gets right (prime 1000 us, enable, hold, then
# move) and this module skipped.
#
# So: US_ARM is sent and HELD first, by arm(), and only then is throttle
# available. And once armed, the resting value of a channel is live frames at
# SLIDER_MIN_US - NOT no frames. Dropping the frames disarms the ESC and the
# next command hits the same refusal all over again. "No frames" is now its
# own explicit action, disarm(), which is the end-of-session step where you
# want to hear the 1/s beep come back.
#
# That also fixed the slider crawling at about 5 us/second near the bottom of
# its travel. With no-frames mapped to the resting position, every drag event
# down there crossed the boundary: tx_servo(pin, 0) to tear the software
# waveform down, then tx_servo(pin, us) to build a new one, on the Tk thread,
# once per motion event. Above the boundary consecutive events only change the
# pulse width, which is cheap - which is why it freed up the moment the motor
# started turning. Keeping the frames live across the whole slider range
# removes the expensive path; the GUI additionally rate-limits the writes so
# finger tracking never waits on lgpio at all.
US_ARM = 1000           # what arm() sends and holds - the ESC's disarm/zero
ARM_HOLD_S = 2.0        # long enough for the ESC to run its arming tones

# SLIDER_MIN_US is the slider's resting position: live frames, armed, and
# below the ESC's 0% point (1100 us) so nothing turns there. 1080 keeps a
# small margin under 1100 while wasting almost none of the travel on values
# that cannot move the motor.
#
# SLIDER_MAX_US is the manual ceiling. THIS IS THE ONE TO CHANGE if you want
# more or less headroom. 1400 us is roughly 40% throttle on this ESC
# (1100 = 0%, 1310 = 25%, 1520 = 50%), which is enough to see direction,
# hear a bearing and watch the current draw, and low enough that a slip of
# the finger on a bench with props fitted is not an event.
SLIDER_MIN_US = 1080
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
    "armed": False,     # frames have been started and held at US_ARM
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


def _emit(channel, us):
    """
    Put `us` on the wire, with no slider clamp. Internal.

    Separate from set_channel() because arm() has to send US_ARM (1000 us),
    which is BELOW SLIDER_MIN_US and would otherwise be clamped up to the
    slider floor - and an ESC armed at 1080 instead of its zero point is the
    bug this whole arming path exists to avoid.

    Returns the value transmitted, or None if the handle has gone.
    """
    h = _handle()
    if h is None:
        raise RuntimeError("GPIO not initialised - power on first")

    us = int(round(us))
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


def set_channel(channel, us):
    """
    Command one channel. Returns the value actually transmitted.

    Values are CLAMPED into [SLIDER_MIN_US, US_MAX_ALLOWED] - they are never
    turned into "frames off". Switching the waveform off is disarm()'s job and
    nothing else's, because an ESC that loses its signal disarms and has to be
    armed again before it will turn. See the arming note at the top of the file.
    """
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")

    if us is None:
        us = SLIDER_MIN_US

    return _emit(channel, _clamp(us))


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
    _set_state(armed=False)


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
# Arming
# ---------------------------------------------------------------------------

def is_armed():
    with _lock:
        return _state["armed"]


def arm():
    """
    Start the throttle frames and hold them at US_ARM so the ESCs can arm.

    BLOCKING for ARM_HOLD_S - call it from a worker thread.

    This is the step the first version was missing. An ESC refuses to arm if
    the first signal it ever sees is above its zero point, so going straight to
    1200 us got a fast error beep and a motor that would not turn. Holding
    US_ARM (1000 us) first is what the scripted test does, and it is not
    optional.

    Both channels are armed together, even for a one-motor test: the idle ESC
    then sits on live frames at its zero point rather than losing its signal,
    so switching which motor you are testing does not mean arming again.

    Ends with both channels at SLIDER_MIN_US, which is the sliders' resting
    position, so what the hardware is doing and what the GUI shows agree from
    the moment this returns.

    Returns True if the hold completed, False if it was cut short.
    """
    claim()

    clear_abort()
    print(f"[MANUAL PWM] arming both channels at {US_ARM} us for {ARM_HOLD_S:.1f}s")

    for channel in CHANNELS:
        _emit(channel, US_ARM)

    if _interruptible_sleep(ARM_HOLD_S):
        print("[MANUAL PWM] arming aborted - switching the frames off again")
        all_off()
        return False

    # Settle on the sliders' resting value, not on US_ARM, so the readouts and
    # the hardware start out in step.
    for channel in CHANNELS:
        _emit(channel, SLIDER_MIN_US)

    _set_state(armed=True)
    print(f"[MANUAL PWM] armed - both channels idling at {SLIDER_MIN_US} us")
    return True


def disarm():
    """
    Stop the frames on both channels. The ESCs go back to beeping once a second.

    The deliberate counterpart to arm(), and the only thing besides the
    teardown paths that switches the waveform off - see set_channel().
    """
    print("[MANUAL PWM] disarming - frames off, ESCs should beep 1/s")
    all_off()


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
    normal end, abort, or an exception out of tx_servo - the channel comes back
    to SLIDER_MIN_US on the way out.

    Note "back to SLIDER_MIN_US", not "frames off", which is what it used to
    do. Below the ESC's 0% point the motor stops either way, but keeping the
    frames alive keeps the ESC ARMED - so the next press of this button spins
    straight away instead of having to go through arming again. Requires arm()
    to have run first; the GUI keeps this button locked until it has.
    """
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")

    if not is_armed():
        raise RuntimeError("not armed - run arm() first or the ESC will refuse")

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
        # Back to idle with the frames still running, so the ESC stays armed.
        # Wrapped because an emergency stop on another thread may already have
        # closed the handle under us, in which case the frames are gone anyway
        # and there is nothing left to set.
        try:
            set_channel(channel, SLIDER_MIN_US)
            rest = f"idling at {SLIDER_MIN_US} us"
        except Exception as e:
            rest = f"frames gone ({e})"
        _set_state(busy=None)
        print(f"[MANUAL PWM] {channel.upper()} spin {'complete' if completed else 'stopped'}"
              f" - {rest}")

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
        # arm() before spin(), not optional - see the arming note at the top.
        # It claims the pins itself, so there is no separate claim() here.
        if not arm():
            print("arming was interrupted - nothing to spin")
            return
        spin(args.channel, us=args.us, hold_s=args.hold,
             on_tick=lambda r: print(f"  {r:4.1f}s left", end="\r"))
    finally:
        release()
        Hobbywing_Prop_Test.session_power_off()
        Hobbywing_Prop_Test.session_stop_monitor()
        Precharge.CLOSE_SYSTEM()


if __name__ == "__main__":
    main()
