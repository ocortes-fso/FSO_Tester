#!/usr/bin/env python3
"""
esc_gui.py - touchscreen page for the ESC serial telemetry monitor.

Sized for the test box's 800x480 screen and meant to be driven with a finger:
current and RPM in the largest type on the page, everything else underneath.

STILL STANDALONE, AND THAT IS THE POINT
---------------------------------------
This runs as its OWN PROCESS. MasterUI.py launches it with subprocess.Popen and
nothing more - no import, no shared globals, no shared serial port, no shared
gpiochip. The isolation that made this package safe to run during a test is
unchanged:

  * if this page throws, or wedges on a port that never answers, MasterUI is
    not in the traceback and the test box keeps running;
  * if MasterUI is restarted, this keeps logging;
  * it never transmits on the UART. Without --control it touches no GPIO or
    I2C either; with --control it drives the FET (pre-arm check in
    Subcodes/Precharge.py's order), reads the INA228 once for the bus check,
    and drives the throttle PWM on GPIO7 (top) or GPIO5 (bot), via esc_arm.py.

A page inside MasterUI would have given up all of that: one process, one
crash, one stuck read() blocking the Tk thread that is also responsible for
the emergency stop button.

WHY PLAIN TKINTER AND NOT ttkbootstrap
--------------------------------------
Two reasons, both practical:

  * ttkbootstrap resolves a custom style name by searching it for widget-class
    words, which is why GUI/MasterUI.py carries a long comment about never
    naming a style "Menu.TButton". Big-number readouts need custom styles, and
    plain tkinter lets us set colours directly with no name to get wrong.
  * it keeps this package's only dependency pyserial, so it also runs on a
    laptop against a USB-TTL adapter without installing anything.

The colours below are picked to sit next to the test box's "cyborg" theme
rather than to match it exactly.

USAGE
-----
    python3 ESC_Serial/esc_gui.py                      # defaults
    python3 ESC_Serial/esc_gui.py -p /dev/ttyUSB0      # another port
    python3 ESC_Serial/esc_gui.py --windowed           # not fullscreen
"""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import esc_arm
import esc_monitor
import esc_protocol as proto

# --- palette ---------------------------------------------------------------
BG = "#060606"
PANEL = "#141414"
FG = "#e8e8e8"
DIM = "#7a7a7a"
ACCENT = "#0dcaf0"      # live numbers
GOOD = "#198754"
WARN = "#fd7e14"
BAD = "#dc3545"

REFRESH_MS = 100        # label repaint rate; logging runs at full frame rate

# Throttle output: GPIO7 (pin 26), the top motor. Fixed - there is no on-screen
# channel switch. (esc_arm still arms both lines; GPIO5 just idles.)
THROTTLE_CHANNEL = "top"

STEP_BTN = "#343a40"    # throttle step button, not selected
STEP_ON = "#0d6efd"     # throttle step button, currently commanded

# Spin-down, measured from the ESC's own eRPM telemetry. The timer starts at
# the end of the drive command (RAMP: the instant the 1300 us pulses are cut;
# SWEEP: the start of its final idle).
#
# THE STOP IS NOT "THE FIRST 0 eRPM FRAME". Bench logs show the ESC streams
# ~14 frames/s while the motor turns but drops to ONE FRAME EVERY ~2 s once it
# has stopped - so the first 0 frame arrives up to 2 s after the actual stop.
# Instead the stop time is where eRPM reaches 0, extrapolated from the last
# two non-zero frames (capped at the first 0 frame). A stop is confirmed by
# either SPINDOWN_CONFIRM_FRAMES consecutive 0 frames, or a single 0 frame
# that follows a gap > SPINDOWN_SLOW_GAP_S (the ESC's slow standstill rate),
# so one glitched 0 frame mid-coast cannot end the timer.
#
# The ESC also does not stop driving the instant the pulses are cut: on
# signal loss it held the last throttle for ~1.65 s on the bench. That hold
# is detected (throttle input reading 0 again) and shown separately.
#
# Raise SPINDOWN_STOP_ERPM if the ESC reports a small non-zero eRPM at
# standstill. Give up after SPINDOWN_TIMEOUT_S.
SPINDOWN_STOP_ERPM = 0
SPINDOWN_CONFIRM_FRAMES = 2
SPINDOWN_SLOW_GAP_S = 0.5
SPINDOWN_HOLD_SHOW_S = 0.2  # report the ESC's hold only above ~a frame or two
SPINDOWN_TIMEOUT_S = 120.0


class EscGui:
    """
    The page.

    One EscReader on a worker thread, one root.after() loop repainting labels
    from its latest snapshot - the same split MasterUI uses, for the same
    reason: Tk is not thread-safe, and the reader must never wait on a repaint.
    """

    def __init__(self, root, args):
        self.root = root
        self.args = args

        self.reader = None
        self.log = None
        self.stop_event = threading.Event()
        self.started_at = None
        self.after_id = None

        # --- arm control ---------------------------------------------------
        # Off unless asked for AND actually possible (lgpio + Subcodes
        # present), so the same file runs read-only on a laptop.
        # getattr, not args.control: the class is usable from code that builds
        # a partial namespace, and read-only is the safe default to fall back
        # to when the flag is simply absent.
        self.control = bool(getattr(args, "control", False)) and esc_arm.available()
        self.busy = ""              # a blocking call is on a worker thread
        self.fault_latched = False  # a guard trip is escalated once

        # STICKY. The telemetry link usually survives whatever went wrong -
        # the ESC keeps streaming after a guard trip cuts the bus - so without
        # this the 10 Hz repaint puts the ordinary "372 frames/s" line straight
        # back over the reason the test just stopped. The fault has to be the
        # thing left on screen until the operator acts on it.
        self.fault_msg = ""

        # Workers post closures here; _tick drains them on the Tk thread.
        # Same reason MasterUI does it: Tk is not thread-safe, and power_up()
        # and arm() both block for seconds.
        self.ui_queue = queue.Queue()

        # Pulse width last commanded by a throttle step button, or None when
        # the channel is at its armed idle (1080 us) or not armed.
        self.cmd_us = None
        self.step_btns = {}

        # Pulse width the sweep last transmitted, or None when not sweeping.
        self.sweep_us = None

        # Spin-down timer, armed when the sweep enters its final idle phase.
        # t_cut is that time.monotonic() (same clock as the frames' t_mono);
        # result is seconds until eRPM first read 0, set by the reader thread
        # in _spindown_frame. Logging carries on past the end of the sweep
        # until then.
        self._spin_reset()

        root.title("ESC Telemetry")
        root.configure(bg=BG)
        if not args.windowed:
            root.attributes("-fullscreen", True)
        # Escape always gets you out, whatever the window manager is doing -
        # on a bare touchscreen with no title bar that matters.
        root.bind("<Escape>", lambda _e: self.quit())

        self._build()
        self._tick()

    # -- layout ------------------------------------------------------------

    def _build(self):
        root = self.root

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=16, pady=(10, 4))

        tk.Label(head, text="ESC TELEMETRY", bg=BG, fg=ACCENT,
                 font=(None, 20, "bold")).pack(side="left")

        self.port_lbl = tk.Label(
            head, bg=BG, fg=DIM, font=(None, 11),
            text=f"{self.args.port}  @ {self.args.baud} baud   "
                 f"{self.args.poles} poles")
        self.port_lbl.pack(side="left", padx=(16, 0), pady=(8, 0))

        self.dot = tk.Label(head, text="●", bg=BG, fg=DIM,
                            font=(None, 22, "bold"))
        self.dot.pack(side="right")
        self.state_lbl = tk.Label(head, text="STOPPED", bg=BG, fg=DIM,
                                  font=(None, 16, "bold"))
        self.state_lbl.pack(side="right", padx=(0, 8))

        # --- the two numbers that matter -----------------------------------
        # Current and RPM get a panel each and the biggest type on the page,
        # because they are what you are watching while someone else drives the
        # throttle. Everything else is a supporting detail.
        big = tk.Frame(root, bg=BG)
        big.pack(fill="x", padx=16, pady=(2, 6))

        self.amps_lbl, self.amps_peak = self._big_panel(
            big, "CURRENT  (ESC)", "A", side="left")
        self.rpm_lbl, self.rpm_peak = self._big_panel(
            big, "RPM", "", side="left")

        # No shunt on this bench: the battery feeds the ESC directly, so there
        # is no INA228 reading to show next to the ESC's own current.
        self.shunt_lbl = self.shunt_delta = None

        # --- secondary readouts --------------------------------------------
        grid = tk.Frame(root, bg=BG)
        grid.pack(fill="both", expand=True, padx=16)

        self.cells = {}
        fields = [
            ("volts", "Voltage", "V"), ("watts", "Power", "W"),
            ("erpm", "eRPM", ""), ("throttle_pct", "Throttle", "%"),
            ("phase_amps", "Phase current", "A"),
            ("mos_temp_c", "FET temp", "C"), ("cap_temp_c", "Cap temp", "C"),
            ("status_raw", "Status", ""),
        ]
        for i, (key, label, unit) in enumerate(fields):
            self.cells[key] = self._cell(grid, label, unit, i // 4, i % 4)
        for c in range(4):
            grid.columnconfigure(c, weight=1)

        # --- link quality ---------------------------------------------------
        # On screen rather than hidden in the log, because an operator needs to
        # know the difference between "0 A because the motor is idle" and
        # "0 A because the frames are not decoding".
        self.link_lbl = tk.Label(root, text="", bg=BG, fg=DIM,
                                 font=(None, 11), anchor="w")
        self.link_lbl.pack(fill="x", padx=16, pady=(4, 0))

        self.log_lbl = tk.Label(root, text="", bg=BG, fg=DIM,
                                font=(None, 11), anchor="w")
        self.log_lbl.pack(fill="x", padx=16)

        if self.control:
            self._build_control(root)

        # --- buttons --------------------------------------------------------
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", padx=16, pady=(6, 10))

        self.start_btn = self._button(bar, "START", self.start, GOOD)
        self.stop_btn = self._button(bar, "STOP", self.stop, BAD)
        self._button(bar, "RESET PEAKS", self.reset_peaks, "#0d6efd")
        self._button(bar, "CLOSE", self.quit, "#495057")
        self.stop_btn.config(state="disabled")

    def _channel(self):
        """The throttle always drives GPIO7 (pin 26, top motor) on this page."""
        return THROTTLE_CHANNEL

    def _build_control(self, root):
        """
        PWM enable / arm / throttle, driven entirely through esc_arm (software
        PWM on GPIO7/GPIO5). No pulse width is computed here and no ceiling is
        enforced here: the step buttons come from esc_arm.THROTTLE_STEPS_US,
        and esc_arm.set_us() clamps on top of that.
        """
        min_us = esc_arm.limits()[0]

        strip = tk.Frame(root, bg=PANEL, padx=12, pady=10)
        strip.pack(fill="x", padx=16, pady=(8, 0))

        # Row 1: power / arm, and the E-STOP. Full-size buttons - the sweeps
        # moved to row 2, so these no longer have to be squeezed.
        row = tk.Frame(strip, bg=PANEL)
        row.pack(fill="x")

        self.power_btn = self._button(row, "POWER ON", self.power_on, "#0d6efd")
        self.arm_btn = self._button(row, "ARM", self.arm_click, "#0d6efd")
        self.disarm_btn = self._button(row, "DISARM", self.disarm_click,
                                       "#495057")
        self.poweroff_btn = self._button(row, "POWER OFF", self.power_off_click,
                                         "#495057")
        # Loudest thing on the page, same reasoning as the Prop TEST V2 page's
        # emergency stop: it is the one you hit without looking.
        self.estop_btn = tk.Button(
            row, text="E-STOP", command=self.estop, bg=BAD, fg="white",
            activebackground=BAD, activeforeground="white",
            font=(None, 17, "bold"), relief="flat", padx=24, pady=12,
            highlightthickness=0, bd=0)
        self.estop_btn.pack(side="right")

        # Row 2: the two timed runs (workers, so E-STOP stays live and aborts
        # them), the sweep / spin-down status, and the commanded pulse width.
        # Profiles: esc_arm.SWEEP_PROFILE / RAMP_PROFILE - see README.
        srow = tk.Frame(strip, bg=PANEL)
        srow.pack(fill="x", pady=(10, 0))

        self.sweep_btn = self._button(
            srow, "SWEEP", lambda: self.sweep_click(esc_arm.sweep_profile()),
            WARN)
        self.ramp_btn = self._button(
            srow, "RAMP", lambda: self.sweep_click(esc_arm.ramp_profile()),
            WARN)
        for b in (self.sweep_btn, self.ramp_btn):
            b.config(font=(None, 13, "bold"), pady=8)
        self.throttle_lbl = tk.Label(srow, text=f"{min_us} us", bg=PANEL,
                                     fg=ACCENT, font=(None, 15, "bold"))
        self.throttle_lbl.pack(side="right")
        # "SIGNAL OFF - ESC still driving 1.2 s", "... spinning down 1.7 s",
        # then "STOPPED 1.85 s from 595 rpm (held 1.62 s)".
        self.spin_lbl = tk.Label(srow, text="", bg=PANEL, fg=DIM,
                                 font=(None, 12, "bold"))
        self.spin_lbl.pack(side="right", padx=(0, 16))

        # Row 3: fixed throttle steps on GPIO7 - one hardware write per press.
        brow = tk.Frame(strip, bg=PANEL)
        brow.pack(fill="x", pady=(10, 0))
        for i, us in enumerate(esc_arm.THROTTLE_STEPS_US):
            b = tk.Button(
                brow, text=f"{us}", command=lambda u=us: self.set_throttle(u),
                bg=STEP_BTN, fg="white", activebackground=STEP_ON,
                activeforeground="white", disabledforeground="#6c757d",
                font=(None, 15, "bold"), relief="flat", pady=10,
                highlightthickness=0, bd=0)
            b.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))
            brow.columnconfigure(i, weight=1, uniform="step")
            self.step_btns[us] = b

        self._refresh_control()

    def _big_panel(self, parent, title, unit, side):
        panel = tk.Frame(parent, bg=PANEL, padx=14, pady=8)
        panel.pack(side=side, fill="both", expand=True, padx=(0, 10))
        tk.Label(panel, text=title, bg=PANEL, fg=DIM,
                 font=(None, 12, "bold")).pack(anchor="w")
        row = tk.Frame(panel, bg=PANEL)
        row.pack(anchor="w")
        value = tk.Label(row, text="--", bg=PANEL, fg=ACCENT,
                         font=(None, 54, "bold"))
        value.pack(side="left")
        if unit:
            tk.Label(row, text=unit, bg=PANEL, fg=DIM,
                     font=(None, 20, "bold")).pack(side="left",
                                                   anchor="s", pady=(0, 10))
        peak = tk.Label(panel, text="peak --", bg=PANEL, fg=DIM,
                        font=(None, 12))
        peak.pack(anchor="w")
        return value, peak

    def _cell(self, parent, label, unit, row, col):
        box = tk.Frame(parent, bg=PANEL, padx=10, pady=6)
        box.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
        tk.Label(box, text=label, bg=PANEL, fg=DIM,
                 font=(None, 10)).pack(anchor="w")
        val = tk.Label(box, text="--", bg=PANEL, fg=FG,
                       font=(None, 20, "bold"))
        val.pack(anchor="w")
        val.unit = unit        # stashed so _paint does not need a second map
        return val

    def _button(self, parent, text, command, colour):
        b = tk.Button(parent, text=text, command=command, bg=colour, fg="white",
                      activebackground=colour, activeforeground="white",
                      font=(None, 15, "bold"), relief="flat",
                      padx=18, pady=12, highlightthickness=0, bd=0)
        b.pack(side="left", padx=(0, 10))
        return b

    # -- start / stop ------------------------------------------------------

    def start(self):
        if self.reader and self.reader.is_alive():
            return
        if esc_monitor.serial is None:
            self._fault("pyserial not installed: pip3 install pyserial")
            return

        self.stop_event = threading.Event()
        self.started_at = time.monotonic()

        sink = (lambda _d: None)
        if not self.args.no_csv:
            try:
                self.log = esc_monitor.CsvLog(
                    self.args.csv or esc_monitor.default_csv_path(),
                    self.started_at)
                sink = self.log.write
            except OSError as e:
                # A log we cannot open must not stop the readout: watching the
                # numbers is the primary job, recording them is the second one.
                self.log = None
                self._fault(f"log file could not be opened: {e}")

        log_sink = sink

        def frame_sink(d):
            # Every frame passes the spin-down timer before it is logged, so
            # the row where the motor is first seen stopped carries spindown_s.
            self._spindown_frame(d)
            log_sink(d)

        self.reader = esc_monitor.EscReader(
            "esc", self.args.port, self.args.baud, self.args.poles, frame_sink,
            stop_event=self.stop_event)
        self.reader.start()

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def stop(self):
        self.stop_event.set()
        if self.reader:
            self.reader.join(timeout=2.0)
        if self.log:
            self.log.close()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self._set_state("STOPPED", DIM)

    # -- arm control -------------------------------------------------------

    def _worker(self, label, fn, done=None):
        """
        Run a blocking control call off the Tk thread.

        power_up() and arm() both take seconds. Running either on the Tk
        thread would freeze the window - including the E-STOP button, which is
        the one thing that must never be unresponsive.
        """
        if self.busy:
            return
        self.busy = label
        self._refresh_control()

        def body():
            try:
                fn()
                if done:
                    self.ui_queue.put(done)
            except esc_arm.ArmError as e:
                self.ui_queue.put(lambda: self._fault(str(e)))
            except Exception as e:          # noqa: BLE001
                self.ui_queue.put(lambda: self._fault(f"{label} failed: {e}"))
            finally:
                self.ui_queue.put(self._clear_busy)

        threading.Thread(target=body, daemon=True, name=f"esc-{label}").start()

    def _clear_busy(self):
        self.busy = ""
        self._refresh_control()

    def power_on(self):
        # Powering up again is the operator acknowledging the last fault.
        self.fault_latched = False
        self.fault_msg = ""
        # Telemetry first, so the frames that arrive as the ESC boots are
        # recorded rather than missed.
        if not (self.reader and self.reader.is_alive()):
            self.start()
        # Pre-arm check in Subcodes/Precharge.py's order (see esc_arm.py):
        # FET on, settle, bus must reach BUS_MIN_VOLTAGE or FET off again.
        self._worker("power on", lambda: esc_arm.power_up(quiet=True))

    def power_off_click(self):
        self._worker("power off", esc_arm.power_off, done=self._reset_throttle)

    def arm_click(self):
        self._worker("arm", esc_arm.arm)

    def disarm_click(self):
        self._worker("disarm", esc_arm.disarm, done=self._reset_throttle)

    def sweep_click(self, profile):
        """
        Step the selected channel through `profile`, then cut the signal.

        SWEEP (esc_arm.SWEEP_PROFILE: idle 2 s, 1200/1300/1400/1500 us 2 s
        each, idle 3 s) times the spin-down from the start of the final idle.
        RAMP (esc_arm.RAMP_PROFILE: 10 us steps to 1300 us, held 3 s) has no
        final idle, so the spin-down is timed from the signal cut. Either way
        it runs to the first 0 eRPM frame, logging on past the end of the
        profile. The ESC is left disarmed; press ARM again for the next run.
        """
        if not esc_arm.is_armed():
            return
        if not (self.reader and self.reader.is_alive()):
            self._fault("start telemetry first - the spin-down is timed "
                        "from the ESC's eRPM")
            return
        chan = self._channel()
        self._spin_reset()
        self.spin_lbl.config(text="sweeping...", fg=ACCENT)

        def on_step(us):
            # Worker thread: stamp the exact value onto the log immediately
            # (the 10 Hz repaint would lag the ramp), and leave the label
            # to _paint_control. 0 = signal cut.
            self.sweep_us = us
            if self.reader is not None:
                self.reader.annotations = {"cmd_us": us}

        def on_drawdown(t):
            # Worker thread, at the instant the final idle is commanded: note
            # the speed it is coasting down from, then arm _spindown_frame.
            snap = self.reader.snapshot() if self.reader else None
            self.spin_cut_rpm = (snap or {}).get("rpm")
            self.spin_t_cut = t

        def run():
            try:
                t = esc_arm.sweep(chan, profile, on_step=on_step,
                                  on_drawdown=on_drawdown)
                if t is None and self.spin_result is None:
                    # Aborted (E-STOP / disarm): no coast-down to time.
                    self.spin_t_cut = None
                    self.ui_queue.put(lambda: self.spin_lbl.config(
                        text="sweep aborted", fg=WARN))
            finally:
                self.sweep_us = None

        self._reset_throttle()
        self._worker("sweep", run, done=self._reset_throttle)

    def _spin_reset(self):
        self.spin_t_cut = self.spin_result = self.spin_cut_rpm = None
        self.spin_hold = None       # s the ESC kept driving after the command
        self.spin_prev_t = None     # t_mono of the previous frame
        self.spin_nz = []           # last two non-zero (t, erpm) frames
        self.spin_zero_t = None     # t_mono of the first frame in a 0 run
        self.spin_zero_n = 0        # length of the current 0 run
        self.spin_warn = ""

    def _spindown_frame(self, d):
        """
        Reader thread, every frame, once the drive command has ended
        (spin_t_cut set). See the SPINDOWN_* notes at the top of the file.
        The confirming row gets spindown_s so the result is in the CSV, not
        just on screen.
        """
        t_cut = self.spin_t_cut
        if t_cut is None or self.spin_result is not None:
            return
        t = d["t_mono"]
        if t <= t_cut:
            return
        prev_t, self.spin_prev_t = self.spin_prev_t, t

        # When did the ESC actually stop driving? Its throttle INPUT reads 0
        # once it has dropped the signal (immediately at an idle command,
        # after its failsafe hold at a cut). Midpoint of the two frames.
        thr_in = d.get("throttle_req_pct")
        if self.spin_hold is None and thr_in is not None and thr_in <= 0:
            t_end = t if prev_t is None else max(t_cut, (prev_t + t) / 2)
            self.spin_hold = t_end - t_cut

        erpm = d.get("erpm")
        if erpm is None:
            return
        if erpm > SPINDOWN_STOP_ERPM:
            # Still turning: any 0 run so far was a glitch, not a stop.
            self.spin_nz = (self.spin_nz + [(t, erpm)])[-2:]
            self.spin_zero_t = None
            self.spin_zero_n = 0
            return

        if self.spin_zero_n == 0:
            self.spin_zero_t = t
            if not self.spin_nz and (self.spin_cut_rpm or 0) > 0:
                # 0 straight away from real speed: the ESC stopped reporting
                # speed, not the motor stopping.
                self.spin_warn = "eRPM read 0 straight after the cut"
        self.spin_zero_n += 1
        slow = prev_t is not None and t - prev_t > SPINDOWN_SLOW_GAP_S
        if self.spin_zero_n < SPINDOWN_CONFIRM_FRAMES and not slow:
            return

        # Stop time: extrapolate the last two non-zero frames down to 0,
        # never later than the first 0 frame. One frame only: use it.
        t_stop = self.spin_zero_t
        if len(self.spin_nz) == 2:
            (t1, e1), (t2, e2) = self.spin_nz
            if e1 > e2 and t2 > t1:
                t_stop = min(t_stop, t2 + e2 * (t2 - t1) / (e1 - e2))
            else:
                t_stop = min(t_stop, t2)
        elif self.spin_nz:
            t_stop = min(t_stop, self.spin_nz[-1][0])
        self.spin_result = max(0.0, t_stop - t_cut)
        d["spindown_s"] = self.spin_result
        print(f"[ESC GUI] spin-down: {self.spin_result:.3f} s from end of "
              f"drive command to 0 eRPM"
              + (f" (from {self.spin_cut_rpm:.0f} rpm)"
                 if self.spin_cut_rpm is not None else "")
              + (f"; ESC kept driving {self.spin_hold:.2f} s of that"
                 if (self.spin_hold or 0) > SPINDOWN_HOLD_SHOW_S else "")
              + (f" - WARNING: {self.spin_warn}; the ESC may not report "
                 f"coasting speed, so this is not the true stop time"
                 if self.spin_warn else ""))

    def estop(self):
        """
        Hard stop. Runs inline, not on a worker - it must not queue behind
        whatever blocking call is already in flight.
        """
        try:
            esc_arm.emergency_stop("operator pressed E-STOP on the ESC page")
        except Exception as e:          # noqa: BLE001
            print(f"[ESC GUI] e-stop: {e}")
        self._reset_throttle()
        self._fault("EMERGENCY STOP - PWM off, FETs off")
        self._refresh_control()

    def _reset_throttle(self):
        """Forget the commanded step (back to idle) without commanding anything."""
        if not self.control:
            return
        self.cmd_us = None
        self.throttle_lbl.config(text=f"{esc_arm.limits()[0]} us")
        self._highlight_step()

    def _highlight_step(self):
        for us, b in self.step_btns.items():
            colour = STEP_ON if us == self.cmd_us else STEP_BTN
            b.config(bg=colour, activebackground=STEP_ON)

    def set_throttle(self, us):
        """A step button: one hardware write, on the Tk thread (non-blocking)."""
        if not self.control or self.busy or not esc_arm.is_armed():
            return
        try:
            sent = esc_arm.set_us(self._channel(), us)
        except esc_arm.ArmError as e:
            self._fault(str(e))
            return
        self.cmd_us = sent
        # The clamp bit: show what actually went out, not what was asked.
        self.throttle_lbl.config(
            text=f"{sent} us" + (" (clamped)" if sent != us else ""))
        self._highlight_step()

    def _refresh_control(self):
        """Enable only what makes sense in the current state."""
        if not self.control:
            return
        powered = esc_arm.owned()
        armed = esc_arm.is_armed()
        busy = bool(self.busy)

        def st(flag):
            return "normal" if flag and not busy else "disabled"

        self.power_btn.config(state=st(not powered))
        self.arm_btn.config(state=st(powered and not armed))
        self.disarm_btn.config(state=st(powered and armed))
        self.poweroff_btn.config(state=st(powered))
        self.sweep_btn.config(state=st(powered and armed))
        self.ramp_btn.config(state=st(powered and armed))
        # Throttle is reachable only once the ESC is actually armed: commanding
        # it before then is what gets the fast error beep instead of a motor.
        step_state = st(powered and armed)
        for b in self.step_btns.values():
            b.config(state=step_state)
        if not armed and self.cmd_us is not None:
            # Disarmed behind our back (E-STOP, sweep end, power off).
            self._reset_throttle()

    def reset_peaks(self):
        """Clear the peak holds without interrupting the log."""
        r = self.reader
        if not r:
            return
        r.peak_amps = r.peak_phase_amps = r.peak_erpm = None
        r.min_volts = r.max_volts = None
        r.peak_mos_c = r.peak_cap_c = None

    def quit(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.stop()
        # Leaving the page must never leave the arm powered or transmitting -
        # same rule the test box's own pages follow. power_off() is safe when
        # nothing is powered, so this is unconditional.
        if self.control:
            try:
                esc_arm.power_off()
            except Exception as e:          # noqa: BLE001
                print(f"[ESC GUI] power off on exit: {e}")
        self.root.destroy()

    # -- refresh -----------------------------------------------------------

    def _tick(self):
        try:
            # Apply whatever the control workers handed over since last tick.
            while True:
                try:
                    fn = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn()
                except Exception as e:      # noqa: BLE001
                    print(f"[ESC GUI] queued update failed: {e}")

            if self.control:
                self._paint_control()
            self._paint()
        except Exception as e:          # noqa: BLE001 - a bad repaint must not
            # kill the loop, or the page freezes with stale numbers on it and
            # no way to tell that is what happened.
            self.link_lbl.config(text=f"display error: {e}", fg=BAD)
        finally:
            self.after_id = self.root.after(REFRESH_MS, self._tick)

    def _paint(self):
        r = self.reader
        if r is None:
            return

        # Painted before the early returns below: whether we are recording is
        # exactly what you want to know while the link is down, not something
        # to find out after it comes back.
        if self.log:
            self.log_lbl.config(
                text=f"logging {self.log.rows} rows -> {self.log.path}")
        else:
            self.log_lbl.config(text="not logging")

        if not r.connected:
            self._set_state("NO LINK", BAD)
            why = r.last_error or "opening the port"
            self.link_lbl.config(text=f"{why}", fg=BAD)
            return

        d = r.snapshot()
        st = r.reader.stats()

        if d is None:
            self._set_state("NO FRAMES", WARN)
            self.link_lbl.config(
                text=f"port open, nothing decoded yet - resync {st['resyncs']} "
                     f"bytes. Wrong baud, or the frame spec does not match.",
                fg=WARN)
            return

        self._set_state("LIVE", GOOD)

        self.amps_lbl.config(text=_f(d["amps"], 1))
        self.amps_peak.config(text=f"peak {_f(r.peak_amps, 1)} A")
        self.rpm_lbl.config(text=_f(d["rpm"], 0) if d["rpm"] is not None
                            else _i(d["erpm"]))
        self.rpm_peak.config(
            text=f"peak {_f(proto.mech_rpm(r.peak_erpm, self.args.poles), 0)}"
            if self.args.poles else f"peak {_i(r.peak_erpm)} eRPM")

        for key, lbl in self.cells.items():
            v = d.get(key)
            if key == "status_raw":
                lbl.config(text=_i(v), fg=BAD if v else FG)
                continue
            nd = 0 if key in ("watts", "erpm") else 1
            lbl.config(text=_f(v, nd) if isinstance(v, float) else _i(v))

        crc = "unchecked" if d["crc_ok"] is None else (
            "ok" if d["crc_ok"] else "FAIL")
        link = (f"{r.frame_hz:.1f} frames/s   frames {st['frames']}   "
                f"resync {st['resyncs']} B   crc {crc}")
        if st["crc_fails"]:
            link += f"   ({st['crc_fails']} failed)"
        bad_link = st["resyncs"] or st["crc_fails"]
        self.link_lbl.config(text=link, fg=WARN if bad_link else DIM)

        # A latched fault outranks a healthy link: last thing painted wins.
        if self.fault_msg:
            self._set_state("FAULT", BAD)
            self.link_lbl.config(text=self.fault_msg, fg=BAD)

    def _paint_control(self):
        """
        The shunt readout, the annotations, and the guard watch.

        The guard trip is picked up HERE rather than acted on by the telemetry
        thread, for the same reason MasterUI does it on its Tk thread: the
        guard can only abort, it cannot cut power or touch widgets. Latched, so
        one trip escalates once.
        """
        shunt = esc_arm.shunt_state()

        sweep_us = self.sweep_us
        spinning_down = (self.spin_t_cut is not None
                         and self.spin_result is None)
        if spinning_down and (time.monotonic() - self.spin_t_cut
                              > SPINDOWN_TIMEOUT_S):
            self.spin_t_cut = None
            self.spin_lbl.config(
                text=f"spin-down: no 0 eRPM within {SPINDOWN_TIMEOUT_S:.0f} s",
                fg=WARN)
            spinning_down = False
        if spinning_down:
            elapsed = time.monotonic() - self.spin_t_cut
            what = "IDLE" if sweep_us else "SIGNAL OFF"
            if self.spin_hold is None:
                # The ESC has not let go of the throttle yet (failsafe hold).
                self.spin_lbl.config(
                    text=f"{what} - ESC driving {elapsed:.1f} s", fg=WARN)
            else:
                self.spin_lbl.config(
                    text=f"{what} - spinning down {elapsed:.1f} s", fg=WARN)
        elif self.spin_result is not None:
            rpm0 = self.spin_cut_rpm
            hold = self.spin_hold or 0
            if self.spin_warn:
                # Not a trustworthy stop time - say so rather than show green.
                self.spin_lbl.config(
                    text=f"{self.spin_result:.2f} s? no coast eRPM", fg=WARN)
            else:
                self.spin_lbl.config(
                    text=f"STOPPED {self.spin_result:.2f} s"
                         + (f" from {rpm0:.0f} rpm" if rpm0 is not None
                            else "")
                         + (f" (held {hold:.2f} s)"
                            if hold > SPINDOWN_HOLD_SHOW_S else ""),
                    fg=GOOD)

        if sweep_us is not None:
            # The sweep worker stamps cmd_us itself; just show where it is.
            self.throttle_lbl.config(text=f"{sweep_us} us")
        elif spinning_down:
            # Past the end of the sweep: keep cmd_us = 0 on every row until
            # the motor is stopped, so the coast-down is unambiguous in the CSV.
            if self.reader is not None:
                self.reader.annotations = {"cmd_us": 0}
        elif self.reader is not None:
            # Stamped onto every logged frame.
            self.reader.annotations = {
                "cmd_us": ((self.cmd_us or esc_arm.limits()[0])
                           if esc_arm.is_armed() else None),
            }

        if self.shunt_lbl is not None:
            sh_a = shunt.get("amps")
            self.shunt_lbl.config(text=_f(sh_a, 1))
            esc_a = (self.reader.snapshot() or {}).get("amps") if self.reader \
                else None
            if sh_a is not None and esc_a is not None and abs(sh_a) > 0.5:
                # The ratio, not the difference: it is the number that goes
                # into SCALES if the two disagree by a constant factor.
                self.shunt_delta.config(
                    text=f"ESC/shunt x{esc_a / sh_a:.3f}")
            else:
                self.shunt_delta.config(text=f"bus {_f(shunt.get('volts'), 2)} V")

        reason = shunt.get("abort_reason")
        if reason and not self.fault_latched:
            self.fault_latched = True
            print(f"[ESC GUI] guard tripped: {reason}")
            self.estop()
            self._fault(f"GUARD TRIPPED: {reason}")

        self._refresh_control()

    def _set_state(self, text, colour):
        self.state_lbl.config(text=text, fg=colour)
        self.dot.config(fg=colour)

    def _fault(self, msg):
        self.fault_msg = msg
        self._set_state("FAULT", BAD)
        self.link_lbl.config(text=msg, fg=BAD)


def _f(v, nd):
    return "--" if v is None else f"{v:.{nd}f}"


def _i(v):
    return "--" if v is None else str(v)


def main():
    p = argparse.ArgumentParser(
        description="Touchscreen ESC telemetry page. Read-only; never "
                    "transmits. Runs as its own process.")
    p.add_argument("-p", "--port", default=proto.DEFAULT_PORT)
    p.add_argument("-b", "--baud", type=int, default=proto.DEFAULT_BAUD)
    p.add_argument("--poles", type=int, default=proto.DEFAULT_POLES)
    p.add_argument("--csv", metavar="FILE")
    p.add_argument("--no-csv", action="store_true")
    p.add_argument("--control", action="store_true",
                   help="also drive the arm: FET pre-arm check (Precharge.py "
                        "order), software PWM throttle on GPIO7 (top motor), "
                        "throttle step buttons, sweep + ramp. Needs the Pi")
    p.add_argument("--windowed", action="store_true",
                   help="do not go fullscreen")
    p.add_argument("--autostart", action="store_true",
                   help="begin reading immediately instead of waiting for START")
    args = p.parse_args()

    root = tk.Tk()
    root.geometry("800x480")
    app = EscGui(root, args)
    root.protocol("WM_DELETE_WINDOW", app.quit)
    if args.autostart:
        app.start()
    root.mainloop()


if __name__ == "__main__":
    main()
