#!/usr/bin/env python3
"""
esc_capture.py - run a telemetry capture end to end, no second pair of hands.

Bench: battery wired straight to the ESC, ESC throttle on GPIO7 (top) or
GPIO5 (bot) as software PWM, ESC telemetry on the Pi 5 UART debug port. No FET,
no I2C, no shunt.

Enables the PWM lines, arms the ESC, walks a list of commanded pulse widths,
logs the ESC's telemetry, saves the raw bytes, and switches the PWM off -
including on Ctrl-C and on an exception.

NOTHING SPINS BY DEFAULT
------------------------
The default phase list stops at 1080 us. The ESC's 0% point is 1100 us and its
arming hold is 1000 us, so the default run powers up, arms, and sits below the
threshold where the motor turns. That is a complete structural capture - frame
length, header, checksum, sequence counter, voltage, temperatures, and the
throttle columns at three distinct commanded values - with the motor stationary.

Add --spin to include phases above 1100 us, once a motor can be turned. Those
are the phases that identify the RPM and current columns, and they are the only
reason to fit a prop.

    # structural capture, nothing turns
    python3 ESC_Serial/esc_capture.py

    # with rotation, once you can: 1%, 25%, back to idle
    python3 ESC_Serial/esc_capture.py --spin

    # custom steps and holds
    python3 ESC_Serial/esc_capture.py --steps 1080,1150,1200 --hold 8

ONE OWNER OF THE THROTTLE LINES
-------------------------------
esc_arm.power_up() claims GPIO5/GPIO7 and refuses if another process (the test
box GUI) holds them. There are NO over-current / under-voltage guards on this
bench: the battery feeds the ESC directly. Stay by the battery connector.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import esc_arm
import esc_monitor
import esc_protocol as proto

# Below the ESC's 0% point (1100 us), so the motor cannot turn.
NO_SPIN_STEPS = [1080]

# With --spin. 1150 is the datasheet's 1%, 1200 is Manual_PWM_Test's canned
# nudge value, 1310 is 25%. Deliberately short of that module's 1400 us
# ceiling: identifying which byte column is RPM does not need more.
SPIN_STEPS = [1080, 1150, 1200, 1310, 1080]

_abort = threading.Event()

# Last time the \r status line was written, so _say() knows whether it has a
# line to clear. Defined above _say() because _say() reads it.
_last_print = [0.0]


def _say(msg):
    # Clear the \r status line first, or the banner lands in the middle of it.
    if _last_print[0]:
        sys.stdout.write("\r" + " " * 100 + "\r")
        _last_print[0] = 0.0
    print(f"[CAPTURE] {msg}", flush=True)


def _hold(reader, seconds, phase, cmd_us=None):
    """
    Sit in one phase for `seconds`, annotating every logged frame.

    The INA228 reading is refreshed into the annotations about 10x a second, so
    each ESC frame is stamped with a shunt measurement taken at nearly the same
    moment. That pairing is what the calibration depends on.

    Returns False if the hold was cut short by an abort or a guard trip.
    """
    _say(f"{phase}: {seconds:.1f}s"
         + (f" at {cmd_us} us" if cmd_us is not None else ""))
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if _abort.is_set():
            _say("aborted")
            return False

        shunt = esc_arm.shunt_state()
        if shunt.get("abort_reason"):
            _say(f"GUARD TRIPPED: {shunt['abort_reason']}")
            return False

        reader.annotations = {
            "phase": phase,
            "cmd_us": cmd_us,
            "shunt_volts": shunt.get("volts"),
            "shunt_amps": shunt.get("amps"),
        }

        d = reader.snapshot()
        if d:
            _say_line(reader, d, shunt, end - time.monotonic())
        _abort.wait(0.1)
    return True


def _say_line(reader, d, shunt, remaining):
    """One updating status line, at 2 Hz rather than 10."""
    now = time.monotonic()
    if now - _last_print[0] < 0.5:
        return
    _last_print[0] = now
    esc_a = d.get("amps")
    sh_a = shunt.get("amps")
    sys.stdout.write(
        f"\r    {remaining:4.1f}s left  "
        f"eRPM {_i(d.get('erpm')):>6}  rpm {_f(d.get('rpm'), 0):>6}  "
        f"ESC {_f(esc_a, 2):>7} A  "
        + (f"shunt {_f(sh_a, 2):>7} A  " if sh_a is not None else "") +
        f"{_f(d.get('volts'), 2):>6} V   "
    )
    sys.stdout.flush()


def _f(v, nd):
    return "--" if v is None else f"{v:.{nd}f}"


def _i(v):
    return "--" if v is None else str(v)


def run(args):
    steps = (
        [int(s) for s in args.steps.split(",")] if args.steps
        else (SPIN_STEPS if args.spin else NO_SPIN_STEPS)
    )

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or esc_monitor.LOG_DIR
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, f"capture_{stamp}.csv")
    bin_path = os.path.join(out_dir, f"capture_{stamp}.bin")

    _say(f"port {args.port} @ {args.baud}, {args.poles} poles")
    _say(f"phases: {' -> '.join(str(s) + 'us' for s in steps)}, "
         f"{args.hold:.0f}s each")
    if max(steps) > 1100:
        _say("NOTE: steps above 1100 us WILL turn the motor. Prop and arm "
             "secured?")
    _say(f"csv {csv_path}")
    _say(f"raw {bin_path}")

    log = esc_monitor.CsvLog(csv_path, time.monotonic())
    raw = open(bin_path, "wb")

    reader = esc_monitor.EscReader(
        args.channel, args.port, args.baud, args.poles, log.write,
        stop_event=_abort, raw_sink=raw.write)

    completed = False
    try:
        # Telemetry first: the ESC is on the battery already, so this is the
        # baseline with no throttle pulses at all.
        reader.annotations = {"phase": "no-pwm"}
        reader.start()
        time.sleep(1.0)
        if reader.last_error:
            _say(f"serial: {reader.last_error}")

        _say(f"claiming PWM lines (GPIO{esc_arm.CHANNELS[args.channel]} = {args.channel})")
        esc_arm.power_up(quiet=True)

        # Lines claimed, no pulses: the ESC should beep once a second.
        if not _hold(reader, args.hold, "no-frames"):
            return

        # arm() blocks for its own hold at 1000 us, so the annotation is set
        # BEFORE the call and the frames that arrive during the hold are
        # labelled correctly. Labelling a hold "arming" and then arming
        # afterwards, which is what this did first, puts the label on the wrong
        # frames - and those frames are the ones that show what the ESC reports
        # at a known 1000 us.
        reader.annotations = {"phase": "arming", "cmd_us": esc_arm.US_ARM}
        _say("arming: holding 1000 us, then settling at 1080 us - nothing turns")
        if not esc_arm.arm():
            _say("arming was interrupted")
            return

        for us in steps:
            if _abort.is_set():
                return
            sent = esc_arm.set_us(args.channel, us)
            if not _hold(reader, args.hold, f"{sent}us", cmd_us=sent):
                return

        completed = True

    except esc_arm.ArmError as e:
        _say(f"REFUSED: {e}")
    except KeyboardInterrupt:
        _say("interrupted")
    finally:
        print()
        _abort.set()
        reader.join(timeout=2.0)

        _say("disarming, PWM off")
        try:
            esc_arm.disarm()
        finally:
            esc_arm.power_off()

        log.close()
        raw.close()

        st = reader.reader.stats()
        print("\n" + "=" * 64)
        print(f"{'COMPLETE' if completed else 'STOPPED EARLY'}")
        print(f"  frames decoded   {st['frames']}")
        print(f"  resync bytes     {st['resyncs']}")
        print(f"  crc failures     {st['crc_fails']}")
        print(f"  peak ESC current {_f(reader.peak_amps, 2)} A")
        print(f"  peak eRPM        {_i(reader.peak_erpm)}")
        print(f"  csv              {csv_path}  ({log.rows} rows)")
        print(f"  raw              {bin_path}  "
              f"({os.path.getsize(bin_path)} bytes)")
        print("=" * 64)
        if st["frames"] == 0 and os.path.getsize(bin_path) == 0:
            print("\nNothing arrived at all. See README section 2 - the serial"
                  "\nconsole on /dev/ttyAMA0 is the usual cause.")
        else:
            print(f"\nNext: python3 ESC_Serial/esc_sniff.py --analyze "
                  f"{bin_path}")


def main():
    p = argparse.ArgumentParser(
        description="Scripted ESC telemetry capture: software PWM on GPIO7/"
                    "GPIO5, arms the ESC, walks a throttle list, logs, PWM off. "
                    "Battery wired straight to the ESC.")
    p.add_argument("-p", "--port", default=proto.DEFAULT_PORT)
    p.add_argument("-b", "--baud", type=int, default=proto.DEFAULT_BAUD)
    p.add_argument("--poles", type=int, default=proto.DEFAULT_POLES)
    p.add_argument("-c", "--channel", default="top",
                   help="throttle line: top = GPIO7 (pin 26), bot = GPIO5 "
                        "(pin 29). Default top")
    p.add_argument("--hold", type=float, default=10.0,
                   help="seconds per phase (default 10)")
    p.add_argument("--steps", help="comma-separated pulse widths in us")
    p.add_argument("--spin", action="store_true",
                   help="include phases above 1100 us, which WILL turn the "
                        "motor")
    p.add_argument("--out", help=f"output directory (default "
                                 f"{esc_monitor.LOG_DIR})")
    args = p.parse_args()

    if esc_monitor.serial is None:
        sys.exit("pyserial is not installed. `pip3 install pyserial "
                 "--break-system-packages`")
    if not esc_arm.available():
        sys.exit("This needs lgpio for the throttle PWM. Run it on the Pi, "
                 "or use esc_monitor.py read-only.")

    # Ctrl-C must reach the hold loops AND leave the teardown in finally to do
    # its job - so it sets the flag rather than raising through the sequence.
    signal.signal(signal.SIGINT, lambda *_: _abort.set())
    signal.signal(signal.SIGTERM, lambda *_: _abort.set())

    run(args)


if __name__ == "__main__":
    main()
