#!/usr/bin/env python3
"""
Hobbywing_Prop_Test.py
======================
Prop test for the FSO Propullsion Arms (Raspberry Pi 5).

Signal generation
-----------------
TOP ESC -> GPIO7      BOT ESC -> GPIO5

Neither GPIO5 nor GPIO7 is wired to the Pi 5 hardware PWM peripheral (that is
GPIO12/13/18/19 only), so the throttle frames have to be produced in software.
We use lgpio.tx_servo(), which is lgpio's software waveform generator: a timing
thread inside the lg library toggles the pin through the gpiochip character
device. That gives us the 1 us resolution and the 50 Hz frame rate the
Hobbywing datasheet asks for, without needing a hardware PWM channel.

Throttle map (from the ESC datasheet)
-------------------------------------
    1000 us  below the 0% point -> valid frame, ESC will NOT arm or spin (safety)
    1150 us  1%
    1310 us  25%
    1520 us  50%
    1690 us  70%
    no pulses at all -> ESC beeps once per second (powered, no throttle signal)

Test sequence
-------------
    1. Power up (precharge -> main FET), no PWM, listen for the 1 Hz beeps.
    2. Prime the commanded value at 1000 us.
    3. Activate the outputs (first frame the ESC ever sees is 1000 us).
    4. TOP test      5. BOT test      6. BOTH test      7. Pulse test
    8. Stop the frames, listen for the beeps again.
    9. Power down (FET off, precharge off, release the gpiochip).

Voltage and current come from the INA228 across the shunt (Subcodes/Batt_monitor)
and are sampled continuously in a background thread: printed live and written to
a CSV in Logs/ at the repo root. A run that finishes without a fault deletes its
own log; the ones that survive are pruned after LOG_RETENTION_DAYS.

Usage
-----
    python3 Subcodes/Hobbywing_Prop_Test.py              # full sequence, asks to confirm
    python3 Subcodes/Hobbywing_Prop_Test.py --yes        # no confirmation prompt
    python3 Subcodes/Hobbywing_Prop_Test.py -p top,bot   # only some phases
    python3 Subcodes/Hobbywing_Prop_Test.py --no-power   # signals only, FET stays shut
"""

import argparse
import csv
import os
import signal
import sys
import threading
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import lgpio

#####*****CHANGES*****#####
# LED added: the session API has to kill the LED on an emergency stop. No
# circular import - LED only pulls in Precharge, which we already use.
from Subcodes import Batt_monitor, LED, Precharge
#####*****END CHANGES*****#####


# ---------------------------------------------------------------------------
# Hardware configuration
# ---------------------------------------------------------------------------

# We always reuse Precharge.h as the gpiochip handle. Opening a second handle
# on the same chip would fight over the line claims.
PWM_TOP = 7          # GPIO7  -> TOP ESC throttle signal
PWM_BOT = 5          # GPIO5  -> BOT ESC throttle signal

PWM_FREQ_HZ = 400     # ESC frame rate

# Throttle setpoints, in microseconds.
US_SAFE = 1000       # safety / disarmed
US_0 = 1150          # 1%
US_25 = 1310         # 25%
US_50 = 1520         # 50%
US_60 = 1600         # ~60%, interpolated, only used by the pulse test
US_70 = 1690         # 70%

# Hard clamp. Nothing in this script may ever command more than 70%.
US_MIN_ALLOWED = US_SAFE
US_MAX_ALLOWED = US_70


# ---------------------------------------------------------------------------
# Timings
# ---------------------------------------------------------------------------

BEEP_LISTEN_S = 6.0     # step 1 and step 8: powered, no frames, listening
SAFETY_HOLD_S = 2.0     # how long we sit at 1000 us between phases
STOP_HOLD_S = 3.0       # "1100 us to stop" - lets the props spin down before 1000 us
PHASE_GAP_S = 2.0       # pause between phases so the operator can look and listen

TELEM_HZ = 5.0          # voltage/current sample + print rate


# ---------------------------------------------------------------------------
# Precharge thresholds
# ---------------------------------------------------------------------------
# Matches GUI/MasterUI.py. 21 V is the "bus cap is charged" point for the
# nominal 6S pack on this rig - change it if you move to a different pack.
PRECHARGE_MIN_VOLTAGE = 21.0
PRECHARGE_TIMEOUT_S = 3.0
PRECHARGE_GOOD_COUNT = 2        # consecutive good reads before we close the FET
PRECHARGE_POLL_S = 0.2

#####*****CHANGES*****#####
# Precharge is disabled (faulty hardware, see Precharge.py). The four constants
# above belong to the wait-for-bus-voltage loop that went with it; they are left
# here for the PCB redesign. What runs instead is a single bus-voltage check
# AFTER the FETs close, and these are its knobs. The threshold and the settle
# time live in Precharge.py so the Arm Test page and this module cannot disagree.
BUS_CHECK_SAMPLES = 5
BUS_CHECK_INTERVAL_S = 0.05
#####*****END CHANGES*****#####

#####*****CHANGES*****#####
# MOVED to Precharge.BUS_DEAD_MAX_V.
#
# The INA228 is on the OUTPUT of the MOSFETs, so with them open it reads roughly
# nothing and anything above this threshold means trouble: residual charge in the
# ESC capacitors, a FET that is not actually opening, or a feed wired past the
# switch. It lives in Precharge.py now, next to BUS_MIN_VOLTAGE, so the two
# pages share one definition. Used by propv2_idle_readout in the GUI.


# ---------------------------------------------------------------------------
# Logging policy
# ---------------------------------------------------------------------------
# Logs live in their own folder, outside the source tree, and a clean run
# throws its log away: the only ones worth keeping are the ones with something
# to diagnose. Those are then pruned after LOG_RETENTION_DAYS so the folder
# cannot grow forever on a rig that nobody tidies up.
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Logs"
)
LOG_PREFIX = "prop_test_"
LOG_RETENTION_DAYS = 4

# Set when the current log is worth keeping:
#   * a guard trip (over-current / under-voltage)
#   * a failed precharge
#   * an exception out of a phase
#   * the operator cancelling a phase, or hitting EMERGENCY STOP - if you
#     reached for either, you reached for it for a reason, and the trace is
#     what tells you what it was
#
# The case that bins its log is a run ended with the normal POWER OFF button.
# Nothing went wrong, so there is nothing to read.
_log_keep = False


def mark_log_keep(reason):
    """Flag the current log as worth keeping. Safe to call from any thread."""
    global _log_keep
    if not _log_keep:
        print(f"[LOG] will be kept: {reason}")
    _log_keep = True


def prune_logs(log_dir=None, max_age_days=LOG_RETENTION_DAYS):
    """
    Delete kept logs older than max_age_days. Returns how many went.

    Called when a run starts and when the GUI page opens, so pruning happens
    as a side effect of using the rig rather than needing a cron job.
    """
    log_dir = log_dir or LOG_DIR
    if not os.path.isdir(log_dir):
        return 0

    cutoff = time.time() - max_age_days * 86400
    removed = 0

    for name in os.listdir(log_dir):
        if not (name.startswith(LOG_PREFIX) and name.endswith(".csv")):
            continue
        path = os.path.join(log_dir, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError as e:
            print(f"[LOG] could not prune {name}: {e}")

    if removed:
        print(f"[LOG] pruned {removed} log(s) older than {max_age_days} days")
    return removed


def _new_log_path(log_dir=None):
    """Reset the keep flag, prune old logs, and name this run's CSV."""
    global _log_keep
    _log_keep = False

    log_dir = log_dir or LOG_DIR
    os.makedirs(log_dir, exist_ok=True)
    prune_logs(log_dir)

    return os.path.join(
        log_dir, f"{LOG_PREFIX}{time.strftime('%Y%m%d_%H%M%S')}.csv"
    )


def _finish_log(telem, path):
    """
    Close the CSV, then keep it only if mark_log_keep() was called.

    Returns the surviving path, or None if the log was discarded.

    stop_log() blocks until the telemetry thread has actually closed the file -
    deleting it first would fail outright on Windows, and on Linux would leave
    the thread writing into an unlinked handle.
    """
    if telem is not None:
        telem.stop_log()

    if not path or not os.path.exists(path):
        return None

    if _log_keep:
        print(f"[LOG] kept: {path}")
        return path

    try:
        os.remove(path)
        print("[LOG] clean run - log discarded")
    except OSError as e:
        print(f"[LOG] could not delete {path}: {e}")
    return None
#####*****END CHANGES*****#####


# ---------------------------------------------------------------------------
# Protection limits  ***  SET THESE FOR YOUR OWN HARDWARE  ***
# ---------------------------------------------------------------------------
# These are placeholders. Put in the real numbers for your pack, shunt, wiring
# and props before running with propellers fitted - they are the only thing
# that will cut the test short if something goes wrong mechanically.
MAX_CURRENT_A = 60.0            # abort above this
MIN_VOLTAGE_V = 22.0            # abort below this (pack sag / pack disconnected)
GUARD_TRIP_COUNT = 3            # consecutive bad samples before aborting.
                                # Debounced because a single I2C glitch or a
                                # transient inrush spike is not a real fault.


# ---------------------------------------------------------------------------
# Sequence definition
# ---------------------------------------------------------------------------
# The sequence is data, not code. Every phase is a (name, channels, steps)
# tuple and every step is a (label, microseconds, seconds) tuple. The runner
# below walks this table, so changing a hold time or inserting a step means
# editing one line here instead of touching the control logic.
#
# The trailing "safety" step of each phase (back to 1000 us) is added
# automatically by run_phase(), so it can never be forgotten.

TOP = ("top",)
BOT = ("bot",)
BOTH = ("top", "bot")

SEQUENCE = [
    ("TOP TEST", TOP, [
        ("0%  arm/idle", US_0, 20.0),
        ("25%", US_25, 10.0),
        ("0%  stop", US_0, STOP_HOLD_S),
    ]),
    ("BOT TEST", BOT, [
        ("0%  arm/idle", US_0, 20.0),
        ("25%", US_25, 10.0),
        ("0%  stop", US_0, STOP_HOLD_S),
    ]),
    ("BOTH TEST", BOTH, [
        ("25%", US_25, 15.0),
        ("50%", US_50, 30.0),
        ("70%", US_70, 10.0),
        ("50%", US_50, 10.0),
        ("0%  stop", US_0, STOP_HOLD_S),
    ]),
    ("PULSE TEST", BOTH, [
        ("50%", US_50, 5.0),
        ("0%  stop", US_SAFE, 3.0),
        ("~60%", US_60, 5.0),
        ("0%  stop", US_SAFE, 3.0),
        ("70%", US_70, 5.0),
        ("0%  stop", US_0, 3.0),
    ]),
]

# Lets --phases pick a subset by short name.
PHASE_KEYS = {"top": 0, "bot": 1, "both": 2, "pulse": 3}


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_stop_event = threading.Event()     # operator / GUI abort
_i2c_lock = threading.Lock()        # Batt_monitor shares one SMBus object
_state_lock = threading.Lock()

_state = {
    "phase": "-",
    "step": "-",
    "target_us": None,
    "top_us": None,
    "bot_us": None,
    "volts": None,
    "amps": None,
    "temp_c": None,
    "abort_reason": None,
}


def register_stop_event(event):
    """Let the GUI hand us its own threading.Event so Cancel still works."""
    global _stop_event
    _stop_event = event


def stop_requested():
    return _stop_event.is_set()


def get_state():
    """Snapshot for the GUI status labels."""
    with _state_lock:
        return dict(_state)


def _set_state(**kw):
    with _state_lock:
        _state.update(kw)


def _abort(reason):
    """Flag an abort. The sequence unwinds through its own finally blocks."""
    with _state_lock:
        if _state["abort_reason"] is None:
            _state["abort_reason"] = reason
    _stop_event.set()


def interruptible_sleep(duration, slice_s=0.02):
    """
    sleep() that notices an abort.

    Returns True if the wait was cut short. Every hold in the sequence goes
    through here, so the longest we can ever be deaf to an abort is slice_s.
    """
    end = time.monotonic() + duration
    while True:
        if stop_requested():
            return True
        remaining = end - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(slice_s, remaining))


# ---------------------------------------------------------------------------
# Software PWM layer
# ---------------------------------------------------------------------------

class SoftServoPWM:
    """
    Software-generated servo frames on two ordinary GPIOs.

    Wraps lgpio.tx_servo(). Three reasons this is a class instead of the loose
    module-level functions the old Spin_test.py used:

      * "commanded value" and "outputs live" are separate bits of state, which
        is exactly what the test sequence needs (prime 1000 us, then enable).
      * the clamp lives in one place, so no caller can command past 70%.
      * stopping is symmetric with starting, so the teardown path is obvious.
    """

    def __init__(self, handle, freq_hz=PWM_FREQ_HZ):
        self.h = handle
        self.freq = freq_hz
        self.pins = {"top": PWM_TOP, "bot": PWM_BOT}
        self.commanded = {"top": US_SAFE, "bot": US_SAFE}
        self.live = False

        #####*****CHANGES*****#####
        # Latched once stop() has run. After that every set()/enable() is a
        # no-op. This is what makes the GUI emergency stop race-free: the STOP
        # button runs on the Tk thread and cuts power while a worker thread may
        # still be inside run_phase(). Without this latch that worker's
        # unwinding would push more tx_servo() calls at an already-closed
        # gpiochip handle. Commands after a stop are never wanted.
        self.disabled = False
        #####*****END CHANGES*****#####

    def claim(self):
        """Claim both lines as outputs, driven low (no pulses -> ESC beeps)."""
        for pin in self.pins.values():
            try:
                lgpio.gpio_claim_output(self.h, pin, level=0)
            except lgpio.error:
                # Already claimed by this handle (e.g. the GUI did it). Fine.
                pass

    def prime(self, us):
        """Step 2: set the value the outputs will start at, without emitting."""
        us = self._clamp(us)
        self.commanded = {"top": us, "bot": us}
        _set_state(target_us=us)

    def enable(self):
        """Step 3: start transmitting. First frame out is whatever we primed."""
        if self.disabled:                                  #####*****CHANGES*****#####
            return                                         # stopped means stopped
        self.live = True
        for name, pin in self.pins.items():
            lgpio.tx_servo(self.h, pin, self.commanded[name], self.freq)
        self._publish()

    def set(self, us, channels=BOTH):
        """
        Command `channels` to `us`. Channels not named are left where they are
        - that is what makes the TOP-only and BOT-only phases work: the idle
        motor keeps receiving 1000 us frames rather than losing its signal.
        """
        if self.disabled:                                  #####*****CHANGES*****#####
            return
        us = self._clamp(us)
        for name in channels:
            self.commanded[name] = us
            if self.live:
                #####*****CHANGES*****#####
                # Tolerate a handle that was closed under us by an emergency
                # stop on another thread. The frames are already gone at that
                # point, so there is nothing left to fail at.
                try:
                    lgpio.tx_servo(self.h, self.pins[name], us, self.freq)
                except lgpio.error as e:
                    print(f"[PWM] tx_servo pin={self.pins[name]}: {e}")
                #####*****END CHANGES*****#####
        _set_state(target_us=us)
        self._publish()

    def all_safe(self):
        """Both channels to 1000 us. Used between phases and on every abort."""
        self.set(US_SAFE, BOTH)

    def stop(self):
        """
        Step 8: stop the frames entirely and leave both lines low, so the ESCs
        go back to beeping once per second. tx_servo() with a pulse width of 0
        is lgpio's "switch this waveform off".
        """
        for pin in self.pins.values():
            try:
                lgpio.tx_servo(self.h, pin, 0, self.freq)
                lgpio.gpio_write(self.h, pin, 0)
            except lgpio.error:
                pass
        self.live = False
        self.disabled = True          #####*****CHANGES*****##### latch, see __init__
        self.commanded = {"top": None, "bot": None}
        _set_state(target_us=None, top_us=None, bot_us=None)

    def _clamp(self, us):
        us = int(round(us))
        clamped = max(US_MIN_ALLOWED, min(US_MAX_ALLOWED, us))
        if clamped != us:
            print(f"[PWM] {us} us clamped to {clamped} us")
        return clamped

    def _publish(self):
        _set_state(top_us=self.commanded["top"], bot_us=self.commanded["bot"])


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

class Telemetry(threading.Thread):
    """
    Background voltage / current / temperature sampler.

    Runs in its own thread so the sequence timing never waits on I2C. It owns
    three jobs: print the live line, append to the CSV, and trip the
    over-current / under-voltage guards.

    Batt_monitor keeps a single module-level SMBus object and is not
    thread-safe, so every read goes through _i2c_lock.
    """

    def __init__(self, csv_path=None, guards_enabled=True, quiet=False):
        super().__init__(daemon=True)
        self.period = 1.0 / TELEM_HZ
        self.guards_enabled = guards_enabled
        #####*****CHANGES*****#####
        # The GUI has its own labels, so it starts us with quiet=True: we keep
        # sampling, logging and guarding, but stop spamming the terminal with
        # the \r status line.
        self.quiet = quiet

        # CSV logging and the guards are both switchable while running, because
        # the GUI starts this thread the moment the page opens (so voltage and
        # current are readable before anything is powered) and only turns
        # logging and guarding on once the bus is actually live.
        self._log_lock = threading.Lock()
        self._log_target = csv_path     # path we have been asked to log to
        self._open_path = None          # path currently open
        self._fh = None
        self._writer = None
        # Lets stop_log() block until the file is really closed, so the caller
        # can safely delete it straight afterwards.
        self._log_closed = threading.Event()
        #####*****END CHANGES*****#####
        self._quit = threading.Event()
        self._over_current = 0
        self._under_voltage = 0
        self._t0 = time.monotonic()
        self.peak_current = 0.0
        self.min_voltage = None

    #####*****CHANGES*****#####
    def start_log(self, csv_path):
        """Begin writing rows to csv_path. Opened by the thread on its next tick."""
        with self._log_lock:
            self._log_target = csv_path

    def stop_log(self, timeout=1.5):
        """
        Close the CSV but keep sampling.

        Blocks until the thread has closed the file (or timeout), because the
        caller may be about to delete it.
        """
        had_file = self._open_path is not None
        with self._log_lock:
            self._log_target = None
            self._log_closed.clear()

        if had_file and self.is_alive():
            if not self._log_closed.wait(timeout):
                print("[LOG] warning: timed out waiting for the log to close")

    def set_guards(self, enabled):
        """Arm or disarm the over-current / under-voltage auto-abort."""
        self.guards_enabled = enabled
        self._over_current = 0
        self._under_voltage = 0

    def reset_stats(self):
        """
        Drop the peak/min trackers.

        Called when a run starts, so the summary reports the run itself and not
        the idle period the GUI spends sitting on the page beforehand.
        """
        self.peak_current = 0.0
        self.min_voltage = None
        self._t0 = time.monotonic()

    def _service_log(self):
        """Open, close or re-open the CSV to match whatever was last requested."""
        with self._log_lock:
            target = self._log_target

        if target == self._open_path:
            return

        if self._fh is not None:
            self._fh.close()
            self._fh = None
            self._writer = None
        self._open_path = None

        if target:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            self._fh = open(target, "w", newline="")
            self._writer = csv.writer(self._fh)
            self._writer.writerow([
                "t_s", "phase", "step", "target_us",
                "top_us", "bot_us", "volts", "amps", "watts", "temp_c",
            ])
            self._open_path = target
        else:
            # Transitioned to closed - release anyone waiting in stop_log().
            self._log_closed.set()
    #####*****END CHANGES*****#####

    def run(self):
        try:
            while not self._quit.is_set():
                self._service_log()         #####*****CHANGES*****#####
                self._sample()
                snap = get_state()

                if self._writer:            #####*****CHANGES*****#####
                    volts, amps = snap["volts"], snap["amps"]
                    watts = (volts * amps) if (volts is not None and amps is not None) else None
                    self._writer.writerow([
                        f"{time.monotonic() - self._t0:.2f}",
                        snap["phase"], snap["step"], snap["target_us"],
                        snap["top_us"], snap["bot_us"],
                        _fmt_num(volts, 3), _fmt_num(amps, 3),
                        _fmt_num(watts, 1), _fmt_num(snap["temp_c"], 1),
                    ])
                    self._fh.flush()   # flush every row: if the test trips, the log survives

                if not self.quiet:          #####*****CHANGES*****#####
                    self._print(snap)
                self._quit.wait(self.period)
        finally:
            if self._fh:                    #####*****CHANGES*****#####
                self._fh.close()

    def stop(self):
        self._quit.set()

    def _sample(self):
        with _i2c_lock:
            volts = Batt_monitor.read_battery_voltage()
            amps = Batt_monitor.read_battery_current()
            temp = Batt_monitor.read_battery_temperature()

        _set_state(volts=volts, amps=amps, temp_c=temp)

        if amps is not None and amps > self.peak_current:
            self.peak_current = amps
        if volts is not None and (self.min_voltage is None or volts < self.min_voltage):
            self.min_voltage = volts

        if self.guards_enabled:
            self._check_guards(volts, amps)

    def _check_guards(self, volts, amps):
        # Only guard while frames are actually going out: before the outputs
        # are enabled the bus is unloaded and a low reading means nothing.
        if get_state()["target_us"] is None:
            self._over_current = 0
            self._under_voltage = 0
            return

        if amps is not None and abs(amps) > MAX_CURRENT_A:
            self._over_current += 1
            if self._over_current >= GUARD_TRIP_COUNT:
                reason = f"over-current: {amps:.1f} A > {MAX_CURRENT_A} A"
                mark_log_keep(reason)      #####*****CHANGES*****##### keep the log
                _abort(reason)
        else:
            self._over_current = 0

        if volts is not None and volts < MIN_VOLTAGE_V:
            self._under_voltage += 1
            if self._under_voltage >= GUARD_TRIP_COUNT:
                reason = f"under-voltage: {volts:.2f} V < {MIN_VOLTAGE_V} V"
                mark_log_keep(reason)      #####*****CHANGES*****##### keep the log
                _abort(reason)
        else:
            self._under_voltage = 0

    def _print(self, snap):
        t = time.monotonic() - self._t0
        top = f"{snap['top_us']}" if snap["top_us"] is not None else "off"
        bot = f"{snap['bot_us']}" if snap["bot_us"] is not None else "off"
        volts, amps = snap["volts"], snap["amps"]
        watts = (volts * amps) if (volts is not None and amps is not None) else None

        # \r keeps it on one updating line; the phase banners print() over it.
        sys.stdout.write(
            f"\r[{t:7.1f}s] {snap['phase']:<10} {snap['step']:<14} "
            f"TOP {top:>5} us  BOT {bot:>5} us | "
            f"{_fmt_unit(volts, 'V', 2)}  {_fmt_unit(amps, 'A', 2)}  "
            f"{_fmt_unit(watts, 'W', 0)}   "
        )
        sys.stdout.flush()


def _fmt_num(v, nd):
    return "" if v is None else f"{v:.{nd}f}"


def _fmt_unit(v, unit, nd):
    return f"{'--':>6} {unit}" if v is None else f"{v:6.{nd}f} {unit}"


# ---------------------------------------------------------------------------
# Power sequencing
# ---------------------------------------------------------------------------

def read_bus_voltage(samples=BUS_CHECK_SAMPLES):
    """
    Sample the bus voltage and return the median, or None if nothing read.

    Median of a few samples rather than one: whether we leave the FETs closed
    should not swing on a single I2C glitch, in either direction - a spurious
    low tears down a good bus, a spurious good reading hides a bad one.
    """
    reads = []
    for _ in range(samples):
        with _i2c_lock:
            v = Batt_monitor.read_battery_voltage()
        if v is not None:
            reads.append(v)
        time.sleep(BUS_CHECK_INTERVAL_S)

    if not reads:
        return None
    reads.sort()
    return reads[len(reads) // 2]


def power_up():
    """
    Close the FETs, then confirm the bus actually came up.

    #####*****CHANGES*****#####
    The precharge circuit is faulty and disabled (see Precharge.py), and the
    battery monitor sits on the OUTPUT of the MOSFETs - it reads roughly nothing
    until they conduct. So there is no pre-close check to make: close them, let
    the bus settle, read it, and open them again if it did not reach
    Precharge.BUS_MIN_VOLTAGE.

    Raises RuntimeError whose message is written for the operator - the GUI puts
    it straight on screen - and leaves the FETs open on any failure.
    """
    Precharge.INITIALIZE_SYSTEM()
    Precharge.START_PRECHARGE()         # no-op while precharge is disabled

    if stop_requested():
        Precharge.CLOSE_FET()
        raise RuntimeError("aborted before power up")

    print("[POWER UP] closing FETs")
    Precharge.OPEN_FET()
    Precharge.TURN_OFF_PRECHARGE()

    time.sleep(Precharge.BUS_SETTLE_S)  # let the bus come up before reading it

    volts = read_bus_voltage()
    ok, message = Precharge.classify_bus_voltage(volts)

    if not ok:
        # The bus did not come up: back off rather than sitting there energised.
        Precharge.CLOSE_FET()
        Precharge.TURN_OFF_PRECHARGE()
        print(f"[POWER UP] FETs opened again: {message}")
        raise RuntimeError(message)

    print(f"[POWER UP] bus {message} - live")
    #####*****END CHANGES*****#####


def power_down():
    """Step 9. Safe in any state, including a half-finished power_up()."""
    try:
        Precharge.CLOSE_FET()
        Precharge.TURN_OFF_PRECHARGE()
    except Exception as e:
        print(f"[POWER DOWN] {e}")
    finally:
        Precharge.CLOSE_SYSTEM()


# ---------------------------------------------------------------------------
# Sequence runner
# ---------------------------------------------------------------------------

def run_step(pwm, phase_name, label, us, hold_s, channels):
    _set_state(phase=phase_name, step=label)
    print(f"\n  -> {label:<14} {us} us for {hold_s:g} s on {'+'.join(channels)}")
    pwm.set(us, channels)
    return interruptible_sleep(hold_s)


def run_phase(pwm, phase_name, channels, steps):
    """
    Run one phase, then always drop both channels back to 1000 us.

    The safety step lives in the finally block rather than in the SEQUENCE
    table so that it also runs when the phase is aborted part way through.
    """
    print(f"\n=== {phase_name} ===")
    try:
        for label, us, hold_s in steps:
            if run_step(pwm, phase_name, label, us, hold_s, channels):
                return False
        return True
    finally:
        _set_state(step="safety")
        print(f"\n  -> safety        {US_SAFE} us")
        pwm.all_safe()
        # Unconditional sleep: we want this hold even on the abort path.
        time.sleep(SAFETY_HOLD_S)


def run_full_test(phases=None, do_power=True, guards_enabled=True, log_dir=None,
                  beep_listen_s=BEEP_LISTEN_S):
    """
    Full test. Returns a dict summary.

    phases          list of keys from PHASE_KEYS, or None for all of them
    do_power        False = skip precharge/FET, signals only (scope on the bench)
    guards_enabled  False = do not auto-abort on current/voltage
    log_dir         where the CSV goes, None = LOG_DIR
    """
    _stop_event.clear()
    _set_state(phase="init", step="-", abort_reason=None)

    selected = SEQUENCE if not phases else [SEQUENCE[PHASE_KEYS[p]] for p in phases]

    csv_path = _new_log_path(log_dir)   #####*****CHANGES*****##### resets the fault flag too

    telem = Telemetry(csv_path=csv_path, guards_enabled=guards_enabled)
    pwm = None
    completed = []

    try:
        #####*****CHANGES*****#####
        # Sampling and logging start BEFORE the power-up, not after. power_up()
        # now reads the input voltage and refuses to close the FET if it is bad,
        # and that refusal is exactly the thing worth having a trace of - it was
        # being thrown away because the thread had not opened the CSV yet. This
        # matches session_power_up(), which already did it in this order.
        telem.start()
        #####*****END CHANGES*****#####

        # --- step 1: power up, no frames, listen for the 1 Hz beeps ----------
        if do_power:
            print("\n[1] Powering up")
            power_up()
        else:
            print("\n[1] --no-power: skipping precharge, FET stays open")
            Precharge.INITIALIZE_SYSTEM()

        pwm = SoftServoPWM(Precharge.h)
        pwm.claim()

        _set_state(phase="beeps", step="no signal")
        print(f"\n[1] No throttle signal for {beep_listen_s:g} s - "
              f"the ESCs should beep once per second")
        if interruptible_sleep(beep_listen_s):
            return _summary(telem, completed)

        # --- steps 2 and 3: prime, then enable ------------------------------
        print(f"\n[2] Priming both channels at {US_SAFE} us (safety)")
        pwm.prime(US_SAFE)

        print("[3] Activating outputs")
        _set_state(phase="armed", step="safety")
        pwm.enable()
        if interruptible_sleep(SAFETY_HOLD_S):
            return _summary(telem, completed)

        # --- steps 4 to 7: the phases ---------------------------------------
        for phase_name, channels, steps in selected:
            if not run_phase(pwm, phase_name, channels, steps):
                break
            completed.append(phase_name)
            if interruptible_sleep(PHASE_GAP_S):
                break

        # --- step 8: frames off, beeps again --------------------------------
        _set_state(phase="beeps", step="no signal")
        print(f"\n[8] Stopping the frames, listening for beeps for {beep_listen_s:g} s")
        pwm.stop()
        interruptible_sleep(beep_listen_s)

        return _summary(telem, completed)

    #####*****CHANGES*****#####
    except Exception as e:
        # Anything thrown out of the run - failed precharge included - is a
        # fault, so the log survives for diagnosis.
        mark_log_keep(f"run failed: {e}")
        raise
    #####*****END CHANGES*****#####

    finally:
        # Teardown always runs, in the order that leaves the rig safest:
        # throttle to safe -> frames off -> power off -> telemetry off.
        print()
        if pwm is not None:
            try:
                if pwm.live:
                    pwm.all_safe()
                    time.sleep(0.2)
                pwm.stop()
            except Exception as e:
                print(f"[TEARDOWN] PWM: {e}")

        print("[9] Powering down")
        power_down()

        #####*****CHANGES*****#####
        # Close the log and keep it only if a fault was recorded, then stop the
        # sampler. _finish_log() before telem.stop() so the thread is still
        # alive to close the file handle.
        _finish_log(telem, csv_path)
        #####*****END CHANGES*****#####

        telem.stop()
        if telem.is_alive():          # power_up() may have thrown before we started it
            telem.join(timeout=2.0)
        Batt_monitor.close()


def _summary(telem, completed):
    reason = get_state()["abort_reason"]
    return {
        "completed_phases": completed,
        "aborted": reason is not None or stop_requested(),
        "abort_reason": reason,
        "peak_current_a": round(telem.peak_current, 2),
        "min_voltage_v": None if telem.min_voltage is None else round(telem.min_voltage, 2),
    }


#####*****CHANGES*****#####
# ---------------------------------------------------------------------------
# Session API - used by the "Prop TEST V2" page in GUI/MasterUI.py
# ---------------------------------------------------------------------------
# run_full_test() above is a one-shot: it powers up, runs everything and powers
# down again. The GUI page needs the opposite shape, because there the operator
# drives it: one button precharges and leaves the bus live, then each test
# button runs a single phase on that live bus, and the STOP button tears it all
# down. So the session API splits run_full_test() into its parts and keeps the
# SoftServoPWM + Telemetry objects alive in _session between button presses.
#
# The sequence table, the clamp, the safety step and the guards are all shared
# with the CLI path - none of that is duplicated here.

_session = {"pwm": None, "telem": None, "csv_path": None, "log_open": False}

# Nice names for the GUI buttons, keyed the same way as PHASE_KEYS.
PHASE_TITLES = {
    "top": "TOP Motor Test",
    "bot": "BOT Motor Test",
    "both": "BOTH Motors Test",
    "pulse": "Pulse Test",
}


def phase_duration(key):
    """
    Total seconds a phase will take, for the GUI progress bar.
    Steps plus the safety hold that run_phase() always appends.
    """
    _, _, steps = SEQUENCE[PHASE_KEYS[key]]
    return sum(hold for _, _, hold in steps) + SAFETY_HOLD_S


def session_live():
    """True once the bus is powered and the pins are claimed."""
    return _session["pwm"] is not None


def session_outputs_live():
    """True once we are actually transmitting throttle frames."""
    pwm = _session["pwm"]
    return pwm is not None and pwm.live


def session_csv_path():
    return _session["csv_path"]


def session_monitoring():
    """True while the telemetry thread is sampling."""
    telem = _session["telem"]
    return telem is not None and telem.is_alive()


def session_clear_fault():
    """
    Forget the last abort reason.

    The GUI calls this when the page is opened. Without it, a guard trip from a
    previous visit is still sitting in the state dict, and the page's fault
    watcher reads it as a fresh trip and fires another emergency stop the
    instant you walk back in.
    """
    _stop_event.clear()
    _set_state(abort_reason=None, phase="-", step="-")


def session_start_monitor(quiet=True):
    """
    Start sampling voltage / current / temperature without powering anything.

    Called when the GUI page opens so the readings are live from the start -
    that is what lets the operator spot a miswired pack, a dead shunt or a
    bus that is still charged before they ever press precharge.

    Guards stay disarmed and nothing is logged: there is no test running yet,
    and with the FET open the bus reads near zero, which would trip the
    under-voltage guard instantly.

    Idempotent, and it is the only thing on the page that opens the I2C bus -
    one sampler, one SMBus, no races with Batt_monitor's shared handle.
    """
    if session_monitoring():
        return _session["telem"]

    telem = Telemetry(csv_path=None, guards_enabled=False, quiet=quiet)
    telem.start()
    _session["telem"] = telem
    return telem


def session_finish_log():
    """
    Close this run's CSV and apply the keep-or-bin rule.

    Returns the surviving path, or None if the run was clean and the log was
    discarded.
    """
    # Idempotent: an e-stop finalises the log, and leaving the page would
    # otherwise finalise it a second time and re-report it.
    if not _session["log_open"]:
        return _session["csv_path"]

    kept = _finish_log(_session["telem"], _session["csv_path"])
    _session["log_open"] = False
    _session["csv_path"] = kept
    return kept


def session_stop_monitor():
    """Stop sampling and release the I2C bus. Called when the page is left."""
    session_finish_log()            #####*****CHANGES*****##### bin it if clean

    telem = _session["telem"]
    if telem is not None:
        telem.stop()
        if telem.is_alive():
            telem.join(timeout=2.0)
    _session["telem"] = None
    Batt_monitor.close()
    _set_state(volts=None, amps=None, temp_c=None)


def session_power_up(log_dir=None, guards_enabled=True, quiet=True):
    """
    Steps 1-3 of the sequence, minus the frames.

    Precharge, close the FET, claim the two pins low, then arm the guards and
    start logging on the telemetry thread that is already running. Deliberately
    does NOT start transmitting: with no frames going out the ESCs sit there
    beeping once a second, which is exactly the check the operator wants at
    this point.

    Raises if the precharge does not come up, leaving the FET open.
    """
    if session_live():
        raise RuntimeError("session already powered - press STOP first")

    _stop_event.clear()
    _set_state(phase="init", step="-", abort_reason=None)

    csv_path = _new_log_path(log_dir)

    # Sampling has to be up before the precharge poll: power_up() reads the bus
    # voltage itself, and the operator wants to watch it climb.
    telem = session_start_monitor(quiet=quiet)

    # Log and guards go live BEFORE the precharge, not after. A failed
    # precharge is exactly the case where you want the voltage trace, and it
    # would be missing entirely if logging only started once the bus was up.
    telem.reset_stats()
    telem.set_guards(guards_enabled)
    telem.start_log(csv_path)
    _session["csv_path"] = csv_path
    _session["log_open"] = True

    try:
        power_up()                  # raises on a bus that never came up
    except Exception as e:
        mark_log_keep(f"precharge failed: {e}")
        raise

    pwm = SoftServoPWM(Precharge.h)
    pwm.claim()

    # Re-claim the LED line on this handle and park it low. Needed because an
    # emergency stop closes the gpiochip, so the claim LED.INIT() made when the
    # page was opened died with the old handle - without this the LED button
    # would silently do nothing after a stop/restart cycle.
    LED.INIT()
    LED.LED_OFF()

    _session.update(pwm=pwm)
    _set_state(phase="beeps", step="no signal")
    return csv_path


def session_run_phase(key):
    """
    Run exactly one phase on the live bus. Returns True if it finished.

    Arms the outputs on first use: prime 1000 us (step 2), enable (step 3),
    hold. So the first frame any ESC sees is still 1000 us, same as the CLI
    path, no matter which test button the operator presses first.
    """
    pwm = _session["pwm"]
    if pwm is None:
        raise RuntimeError("not powered - run the precharge first")

    _stop_event.clear()
    _set_state(abort_reason=None)

    if not pwm.live:
        print(f"[2] Priming both channels at {US_SAFE} us (safety)")
        pwm.prime(US_SAFE)
        print("[3] Activating outputs")
        pwm.enable()
        if interruptible_sleep(SAFETY_HOLD_S):
            return False

    name, channels, steps = SEQUENCE[PHASE_KEYS[key]]
    #####*****CHANGES*****#####
    # An exception out of a phase is a fault worth a log. An operator cancel
    # (ok == False) is not - that run still bins its log.
    try:
        ok = run_phase(pwm, name, channels, steps)
    except Exception as e:
        mark_log_keep(f"{name} raised: {e}")
        raise
    #####*****END CHANGES*****#####
    _set_state(phase="ready" if ok else "cancelled", step="safety")
    return ok


def session_cancel_phase():
    """
    Cancel the running phase but keep the bus live.

    Only sets the flag: the worker thread notices inside interruptible_sleep()
    and unwinds through run_phase()'s finally, which drops both channels to
    1000 us and holds. That is a controlled stop, not a power cut - use
    session_emergency_stop() for the power cut.

    The log is kept: cancelling part way through a phase means something made
    you reach for the button, and the trace up to that point is what tells you
    what it was.
    """
    mark_log_keep("phase cancelled by operator")   #####*****CHANGES*****#####
    _abort("cancelled by operator")


def _shutdown(reason, tag, keep_log):
    """
    De-energise the rig. Shared by the normal power-off and the emergency stop,
    which differ only in what they do with the log.

    Order is what matters and it is the reverse of session_power_up():
    throttle to safe, frames off, LED off, FET off, precharge off, chip closed.

    Safe to call from the Tk thread at any time, including while a worker
    thread is mid-phase, and safe to call twice. Frames die before power does,
    and SoftServoPWM.stop() latches `disabled` so the unwinding worker cannot
    push any more commands at the closed handle.
    """
    if keep_log:
        mark_log_keep(reason)
    _abort(reason)

    pwm = _session["pwm"]
    if pwm is not None:
        try:
            if pwm.live:
                pwm.all_safe()      # 1000 us on both channels
                time.sleep(0.1)     # one frame is 20 ms at 50 Hz, so this lands
            pwm.stop()              # frames off -> ESCs go back to beeping
        except Exception as e:
            print(f"[{tag}] PWM: {e}")

    # The LED runs off the same bus as the ESCs, so it goes off with everything
    # else rather than being left lit on a dead rail.
    try:
        LED.LED_OFF()
    except Exception as e:
        print(f"[{tag}] LED: {e}")

    power_down()                    # FET off, precharge off, gpiochip closed

    # Sampling deliberately keeps running, and the I2C bus is NOT closed: the
    # operator still wants to see the bus voltage decay after a stop, and to
    # know the rig is actually dead before touching it. Only the log and the
    # guards go away, because there is no longer a run to log or protect.
    telem = _session["telem"]
    if telem is not None:
        telem.set_guards(False)

    kept = session_finish_log()

    _session.update(pwm=None)
    _set_state(phase="stopped", step="-", target_us=None,
               top_us=None, bot_us=None)
    print(f"[{tag}] complete")
    return kept


def session_power_off():
    """
    Normal end-of-test power-down. The opposite of session_power_up().

    Takes the rig from LIVE back to SAFE without flagging anything wrong, so a
    run that went fine still bins its log. This is the button you want when the
    test is simply finished - reaching for the emergency stop every time would
    make every log a kept one and bury the ones that matter.
    """
    return _shutdown("powered down by operator", "POWER OFF", keep_log=False)


def session_emergency_stop():
    """
    Emergency power-down. Same teardown, but the log is kept.

    Hitting this means something was wrong, so the trace up to that point is
    worth reading - same reasoning as cancelling a phase.
    """
    return _shutdown("emergency stop", "E-STOP", keep_log=True)
#####*****END CHANGES*****#####


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _install_signal_handlers():
    """Ctrl+C sets the abort flag instead of killing us mid-throttle."""
    def handler(signum, frame):
        print("\n[ABORT] signal received, unwinding to safe state")
        _abort("operator interrupt")

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main():
    ap = argparse.ArgumentParser(description="Hobbywing two-ESC prop test")
    ap.add_argument("-p", "--phases", default="",
                    help="comma separated subset of: top,bot,both,pulse")
    ap.add_argument("-y", "--yes", action="store_true",
                    help="skip the confirmation prompt")
    ap.add_argument("--no-power", action="store_true",
                    help="do not precharge or close the FET (signal check only)")
    ap.add_argument("--no-guards", action="store_true",
                    help="disable the over-current / under-voltage auto-abort")
    ap.add_argument("--beep-listen", type=float, default=BEEP_LISTEN_S,
                    help=f"seconds to sit with no signal (default {BEEP_LISTEN_S:g})")
    ap.add_argument("--log-dir", default=None, help="where to write the CSV")
    args = ap.parse_args()

    phases = [p.strip().lower() for p in args.phases.split(",") if p.strip()]
    for p in phases:
        if p not in PHASE_KEYS:
            ap.error(f"unknown phase '{p}', pick from {', '.join(PHASE_KEYS)}")

    _install_signal_handlers()

    print(f"Phases : {', '.join(phases) if phases else 'all'}")
    print(f"Guards : {'off' if args.no_guards else f'{MAX_CURRENT_A} A / {MIN_VOLTAGE_V} V'}")
    print(f"Power  : {'OFF (--no-power)' if args.no_power else 'precharge + FET'}")

    if not args.yes:
        print("\n!! Props will spin. Clear the area, secure the rig, eyes on it. !!")
        if input("Type GO to start: ").strip() != "GO":
            print("Cancelled.")
            return 1

    result = run_full_test(
        phases=phases or None,
        do_power=not args.no_power,
        guards_enabled=not args.no_guards,
        log_dir=args.log_dir,
        beep_listen_s=args.beep_listen,
    )

    print("\n--- RESULT ---")
    print(f"Completed : {', '.join(result['completed_phases']) or 'none'}")
    print(f"Peak      : {result['peak_current_a']} A")
    print(f"Min bus   : {result['min_voltage_v']} V")
    if result["aborted"]:
        print(f"ABORTED   : {result['abort_reason'] or 'stop requested'}")
        return 2
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
