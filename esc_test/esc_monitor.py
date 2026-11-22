#!/usr/bin/env python3
"""
esc_monitor.py - live current / RPM readout and CSV log from Hobbywing ESCs.

STANDALONE. Reads serial, writes a CSV, prints to the terminal. No GPIO, no
I2C, no gpiochip, no throttle output, and not one byte sent to the ESC - so it
cannot interfere with a testbox run, and it can be left recording while
something else drives the motor.

Every decoded frame is logged, at whatever rate the ESC sends (typically tens
of hertz), so the log has the transients in it and not just whatever the screen
happened to show. Both raw counts and scaled engineering values are recorded:
if a scale factor in esc_protocol.py turns out to be wrong, old logs can be
re-derived instead of re-flown.

USAGE
-----
    # one ESC, default port, log to ESC_Serial/logs/
    python3 ESC_Serial/esc_monitor.py

    # explicit port and the motor's pole count, so RPM is real and not eRPM
    python3 ESC_Serial/esc_monitor.py -p /dev/ttyAMA2 --poles 28

    # two ESCs at once, named, for 60 seconds
    python3 ESC_Serial/esc_monitor.py -p top=/dev/ttyAMA2 -p bot=/dev/ttyAMA3 \
            --poles 28 -t 60

    # pick your own log file, or turn logging off
    python3 ESC_Serial/esc_monitor.py --csv ~/run1.csv
    python3 ESC_Serial/esc_monitor.py --no-csv

Ctrl-C stops cleanly: the CSV is flushed and closed and a summary is printed.

READING THE STATUS LINE
-----------------------
    top   49.2 Hz  12345 eRPM   2647 rpm   25.14 V   18.42 A    463 W
          mos 42.1C cap 31.0C  thr 50.2%  | frames 1482 resync 0 crc -

`frames`, `resync` and `crc` are the link-quality counters. Steady resyncs
mean bytes are being dropped or the frame spec is wrong; both are worth
knowing before you trust the numbers. `crc -` means no checksum has been
confirmed yet (see esc_protocol.CRC_NAME).
"""

from __future__ import annotations

import argparse
import csv
import os
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import esc_protocol as proto

try:
    import serial
except ImportError:
    serial = None

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# How long a reader waits before trying a port again after it went away. The
# bench case this is for is power-cycling the ESC, which drops the line: the
# monitor should pick the stream back up on its own rather than needing a
# restart in the middle of a test.
RECONNECT_S = 2.0

_stop = threading.Event()


class EscReader(threading.Thread):
    """
    One serial port -> decoded frames.

    Owns the port, the resync state and the running statistics for one ESC.
    Pushes every frame onto `sink` (the CSV writer's queue) and keeps the most
    recent one in `latest` for the display, so a slow terminal can never cost
    us a logged sample.
    """

    def __init__(self, name, port, baud, poles, sink, stop_event=None,
                 raw_sink=None):
        super().__init__(daemon=True, name=f"esc-{name}")
        self.name_ = name
        self.port = port
        self.baud = baud
        self.poles = poles
        self.sink = sink

        # Optional tap on the undecoded byte stream, so a scripted capture can
        # keep a .bin alongside the CSV: the CSV depends on the frame spec
        # being right, the .bin does not, and it can be re-decoded forever.
        self.raw_sink = raw_sink

        # Extra columns stamped onto every frame by whatever is driving the
        # capture - currently just cmd_us, the commanded pulse width.
        #
        # A plain dict, replaced wholesale by the driver rather than mutated,
        # so a frame can never pick up half of an update. A stale annotation on
        # the one frame either side of a phase change does not matter.
        self.annotations = {}
        # The CLI shares one module-level event across its readers; esc_gui.py
        # passes its own, so a Stop on the page ends that reader without
        # touching anything else in the process.
        self.stop_event = stop_event if stop_event is not None else _stop

        self.reader = proto.FrameReader()
        self.latest = None
        self.connected = False
        self.last_error = None

        # Frame rate, measured rather than assumed - it is the first thing
        # that tells you the link is degrading.
        self._rate_t0 = time.monotonic()
        self._rate_n = 0
        self.frame_hz = 0.0

        # Run statistics for the closing summary.
        self.peak_amps = None
        self.peak_phase_amps = None
        self.peak_erpm = None
        self.min_volts = None
        self.max_volts = None
        self.peak_mos_c = None
        self.peak_cap_c = None

        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    def run(self):
        while not self.stop_event.is_set():
            try:
                self._session()
            except Exception as e:          # noqa: BLE001 - a port that went
                # away must not take the process down: the other ESC may still
                # be streaming, and the log so far is worth keeping.
                self.connected = False
                self.last_error = str(e)
                self.stop_event.wait(RECONNECT_S)
        self.connected = False

    def _session(self):
        # exclusive=True: refuse to share the tty. Two readers on one port
        # split the bytes between them and both decode garbage, which looks
        # exactly like a wiring fault and is not.
        with serial.Serial(self.port, self.baud, timeout=0.1,
                           exclusive=True) as s:
            s.reset_input_buffer()
            self.connected = True
            self.last_error = None
            while not self.stop_event.is_set():
                # Take what has arrived, or block for the next byte. NOT a
                # fixed read(512): at 19200 baud 512 bytes never arrive inside
                # the 0.1 s timeout, so every read waited the full 0.1 s and
                # ~8 frames were stamped with one late t_mono - up to 100 ms
                # of error on anything timed from the frames (spin-down).
                chunk = s.read(s.in_waiting or 1)
                if chunk:
                    if self.raw_sink is not None:
                        self.raw_sink(chunk)
                    for frame in self.reader.feed(chunk):
                        self._on_frame(frame)
                self._update_rate()

    # -- per frame ---------------------------------------------------------

    def _on_frame(self, frame):
        d = proto.decode(frame, poles=self.poles)
        d["t_mono"] = time.monotonic()
        d["esc"] = self.name_
        d["raw_hex"] = frame.hex()
        d.update(self.annotations)

        with self._lock:
            self.latest = d
            self._track(d)
        self._rate_n += 1
        self.sink(d)

    def _track(self, d):
        def hi(cur, val):
            if val is None:
                return cur
            return val if cur is None or val > cur else cur

        self.peak_amps = hi(self.peak_amps, _abs_or_none(d["amps"]))
        self.peak_phase_amps = hi(self.peak_phase_amps,
                                  _abs_or_none(d["phase_amps"]))
        self.peak_erpm = hi(self.peak_erpm, d["erpm"])
        self.peak_mos_c = hi(self.peak_mos_c, d["mos_temp_c"])
        self.peak_cap_c = hi(self.peak_cap_c, d["cap_temp_c"])

        v = d["volts"]
        if v is not None:
            self.max_volts = hi(self.max_volts, v)
            if self.min_volts is None or v < self.min_volts:
                self.min_volts = v

    def _update_rate(self):
        now = time.monotonic()
        dt = now - self._rate_t0
        if dt >= 1.0:
            self.frame_hz = self._rate_n / dt
            self._rate_n = 0
            self._rate_t0 = now

    # -- display -----------------------------------------------------------

    def snapshot(self):
        with self._lock:
            return dict(self.latest) if self.latest else None

    def status_lines(self, width=None):
        """Two lines: the headline numbers, then the secondary ones."""
        tag = f"{self.name_:<5}"
        if not self.connected:
            why = self.last_error or "waiting for the port"
            return [f"{tag} -- no link -- {why}", ""]

        d = self.snapshot()
        if d is None:
            return [f"{tag} connected, no frames decoded yet "
                    f"(resync {self.reader.resyncs})", ""]

        rpm = (f"{d['rpm']:>7.0f} rpm" if d["rpm"] is not None
               else "    -- rpm")
        st = self.reader.stats()
        crc = "-" if d["crc_ok"] is None else ("ok" if d["crc_ok"] else "FAIL")

        # The rate is measured over a 1 s window, so it reads as "--" rather
        # than a confident 0.0 until the first window has closed.
        hz = f"{self.frame_hz:>5.1f}" if self.frame_hz else "   --"

        line1 = (f"{tag} {hz} Hz  "
                 f"{_i(d['erpm']):>7} eRPM  {rpm}  "
                 f"{_f(d['volts'], 2):>7} V  {_f(d['amps'], 2):>7} A  "
                 f"{_f(d['watts'], 0):>6} W")
        line2 = (f"      mos {_f(d['mos_temp_c'], 1)}C  "
                 f"cap {_f(d['cap_temp_c'], 1)}C  "
                 f"thr {_f(d['throttle_pct'], 1)}%  "
                 f"phase {_f(d['phase_amps'], 2)}A  "
                 f"| frames {st['frames']} resync {st['resyncs']} crc {crc}")
        return [line1, line2]

    def summary(self):
        st = self.reader.stats()
        return [
            f"{self.name_}  ({self.port} @ {self.baud})",
            f"    frames {st['frames']}   resyncs {st['resyncs']}   "
            f"crc fails {st['crc_fails']}",
            f"    peak current      {_f(self.peak_amps, 2)} A",
            f"    peak phase current {_f(self.peak_phase_amps, 2)} A",
            f"    peak eRPM         {_i(self.peak_erpm)}"
            + (f"   ({_f(proto.mech_rpm(self.peak_erpm, self.poles), 0)} rpm)"
               if self.poles else "   (set --poles for mechanical RPM)"),
            f"    voltage           {_f(self.min_volts, 2)} - "
            f"{_f(self.max_volts, 2)} V",
            f"    peak temps        mos {_f(self.peak_mos_c, 1)}C   "
            f"cap {_f(self.peak_cap_c, 1)}C",
        ]


def _abs_or_none(v):
    return None if v is None else abs(v)


def _f(v, nd):
    return "--" if v is None else f"{v:.{nd}f}"


def _i(v):
    return "--" if v is None else str(v)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

# Decoded but deliberately not logged. version_raw is constant (0x01) on
# every frame; raw_hex still carries it if it is ever needed.
CSV_EXCLUDED = ("version_raw",)

CSV_COLUMNS = (
    ("iso", "wall-clock time"),
    ("t_s", "seconds since the monitor started"),
    ("cmd_us", "commanded pulse width, when a script is driving one"),
    ("spindown_s", "signal-off to 0 eRPM, on the row where the stop is seen"),
) + tuple((k, "") for k in proto.SCALED_KEYS) \
  + tuple((k, "") for k in proto.RAW_KEYS if k not in CSV_EXCLUDED) \
  + (("crc_ok", ""), ("raw_hex", "the frame, for re-decoding later"))


class CsvLog:
    """
    Append-only CSV, flushed every row.

    Flushed per row on purpose: the runs worth reading are the ones that ended
    badly, and a buffered writer loses exactly the last second before the
    thing you were trying to catch. At a few tens of rows per second the cost
    is irrelevant next to that.
    """

    def __init__(self, path, t0):
        self.path = path
        self.t0 = t0
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._fh = open(path, "w", newline="")
        self._w = csv.writer(self._fh)
        self._w.writerow([c for c, _ in CSV_COLUMNS])
        self._lock = threading.Lock()
        self.rows = 0

    def write(self, d):
        row = []
        for col, _ in CSV_COLUMNS:
            if col == "iso":
                row.append(time.strftime("%Y-%m-%dT%H:%M:%S"))
            elif col == "t_s":
                row.append(f"{d['t_mono'] - self.t0:.3f}")
            else:
                v = d.get(col)
                row.append("" if v is None else
                           (f"{v:.4f}" if isinstance(v, float) else v))
        # One lock for both readers: csv.writer is not thread-safe, and two
        # ESCs logging at 50 Hz each will interleave without it.
        with self._lock:
            self._w.writerow(row)
            self._fh.flush()
            self.rows += 1

    def close(self):
        with self._lock:
            self._fh.close()


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

class Display:
    """
    Repainting status block, two lines per ESC.

    ANSI cursor-up so it updates in place instead of scrolling. --plain turns
    that off, which is what you want when piping to a file or into tee.
    """

    def __init__(self, readers, plain=False):
        self.readers = readers
        self.plain = plain
        self._painted = 0

    def paint(self):
        lines = []
        for r in self.readers:
            lines += r.status_lines()
        if self.plain:
            print(" | ".join(l.strip() for l in lines if l.strip()))
            return
        if self._painted:
            sys.stdout.write(f"\033[{self._painted}A")
        for line in lines:
            sys.stdout.write("\033[2K" + line + "\n")
        sys.stdout.flush()
        self._painted = len(lines)

    def finish(self):
        if not self.plain and self._painted:
            sys.stdout.write("\n")
            sys.stdout.flush()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_ports(specs, default_port):
    """
    -p accepts "name=/dev/tty..." or just "/dev/tty...".

    Names are what appear in the console and in the CSV's `esc` column, so
    "top" and "bot" are worth typing.
    """
    if not specs:
        return [("esc", default_port)]
    out = []
    for i, spec in enumerate(specs):
        if "=" in spec:
            name, _, port = spec.partition("=")
            out.append((name.strip(), port.strip()))
        else:
            out.append((f"esc{i + 1}" if len(specs) > 1 else "esc", spec))
    return out


def default_csv_path():
    return os.path.join(LOG_DIR, time.strftime("esc_%Y%m%d_%H%M%S.csv"))


def main():
    p = argparse.ArgumentParser(
        description="Live current / RPM readout and CSV log from Hobbywing "
                    "ESC serial telemetry. Read-only; never transmits.")
    p.add_argument("-p", "--port", action="append", metavar="[NAME=]DEV",
                   help="serial device, repeatable for several ESCs "
                        f"(default {proto.DEFAULT_PORT})")
    p.add_argument("-b", "--baud", type=int, default=proto.DEFAULT_BAUD,
                   help=f"baud rate (default {proto.DEFAULT_BAUD})")
    p.add_argument("--poles", type=int, default=proto.DEFAULT_POLES,
                   help=f"motor magnet poles, for eRPM -> RPM (default "
                        f"{proto.DEFAULT_POLES}, the X8/8120's 36N40P). "
                        f"0 logs eRPM only and leaves the rpm column empty")
    p.add_argument("-t", "--duration", type=float,
                   help="stop after this many seconds (default: until Ctrl-C)")
    p.add_argument("--hz", type=float, default=5.0,
                   help="screen refresh rate (default 5). Logging is always "
                        "at full frame rate regardless")
    p.add_argument("--csv", metavar="FILE",
                   help=f"log file (default a timestamped one in {LOG_DIR})")
    p.add_argument("--no-csv", action="store_true", help="do not log")
    p.add_argument("--plain", action="store_true",
                   help="scrolling output instead of an in-place block")
    args = p.parse_args()

    if serial is None:
        sys.exit("pyserial is not installed. `pip3 install pyserial` "
                 "(add --break-system-packages on Raspberry Pi OS).")

    ports = parse_ports(args.port, proto.DEFAULT_PORT)
    t0 = time.monotonic()

    log = None
    if not args.no_csv:
        log = CsvLog(args.csv or default_csv_path(), t0)

    sink = (lambda d: None) if log is None else log.write

    readers = [EscReader(name, port, args.baud, args.poles, sink)
               for name, port in ports]

    # Ctrl-C has to reach the reader threads, which are blocked in read().
    # Setting the event lets them fall out of their loops and the port close
    # cleanly; without it the process exits with the tty still claimed.
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())

    print("ESC serial telemetry monitor  (read-only, Ctrl-C to stop)")
    for name, port in ports:
        print(f"  {name:<5} {port} @ {args.baud} baud")
    print(f"  poles: {args.poles or 'unknown - logging eRPM only'}")
    print(f"  log:   {log.path if log else 'disabled'}")
    if proto.CRC_NAME is None:
        print("  note:  no checksum confirmed yet, frames are accepted on "
              "header + length alone")
    print()

    for r in readers:
        r.start()

    display = Display(readers, plain=args.plain)
    period = 1.0 / max(args.hz, 0.5)
    try:
        while not _stop.is_set():
            display.paint()
            if args.duration and time.monotonic() - t0 >= args.duration:
                break
            _stop.wait(period)
    finally:
        _stop.set()
        for r in readers:
            r.join(timeout=2.0)
        display.finish()

        print("\n" + "=" * 60)
        print(f"Run length {time.monotonic() - t0:.1f}s")
        for r in readers:
            for line in r.summary():
                print(line)
        if log:
            log.close()
            print(f"\n{log.rows} rows -> {log.path}")
        print("=" * 60)


if __name__ == "__main__":
    main()
