# esc_test — Hobbywing ESC serial telemetry and throttle test

Standalone live logger for current, RPM and everything else a Hobbywing X-series
ESC puts on its telemetry wire, plus an optional control layer to power the arm,
arm the ESC, command throttle and run a timed sweep / spin-down test.

**Read-only by default.** `esc_protocol`, `esc_sniff`, `esc_monitor` and `esc_gui`
without `--control` import nothing from `Subcodes/` or `GUI/`, touch no GPIO and no
I²C, and never transmit a byte to the ESC. You can leave any of them recording while
something else drives the motor.

**`esc_arm.py` is the one exception, and it is opt-in.** It powers the arm through the
FETs, arms the ESC and commands throttle, calling `Subcodes/Precharge.py` and
`Subcodes/Batt_monitor.py` rather than reimplementing them. `esc_capture.py` and
`esc_gui.py --control` are the two things that use it. Only one process may own the
FET and throttle lines at a time; see §5.

```
esc_test/
├── esc_protocol.py   frame spec, scale factors, checksum, decoder
├── esc_sniff.py      bench tool: confirm the frame format and the scale factors
├── esc_monitor.py    live readout + CSV logger, for a terminal
├── esc_gui.py        touchscreen page: readout, logging, throttle steps, sweep
├── esc_capture.py    scripted capture: powers the arm, arms, holds, logs, powers down
├── esc_arm.py        the only file that touches hardware - optional, see below
└── logs/             timestamped CSVs and raw captures
```

---

## 1. Wiring

The ESC telemetry line is a single 3.3 V TTL output: the ESC talks, nothing listens
back. Two wires:

| ESC | Raspberry Pi 5 |
|---|---|
| telemetry / TLM (signal out) | **RX** on the UART debug connector |
| GND | GND on the same connector |

For `--control` / `esc_capture.py` (battery → FETs → INA228 → ESC → motor; precharge
is disabled, see `Subcodes/Precharge.py`), add the throttle signal:

| ESC | Raspberry Pi 5 |
|---|---|
| white (PWM throttle in) | **GPIO7, pin 26** (`top`) or **GPIO5, pin 29** (`bot`) — software PWM, 400 Hz |
| black (signal GND) | GND, pin 25 or 30 |

Do **not** connect the Pi's TX to the ESC. One UART reads one ESC; to read the other
one, move the single wire across.

### Pulse widths

All in `esc_arm.py`:

| | µs | |
|---|---|---|
| `US_ARM` | 1000 | held for 2 s while the ESC arms |
| `IDLE_US` (`SLIDER_MIN_US`) | 1080 | armed resting value — below the 0% point, nothing turns |
| `ZERO_PCT_US` | 1100 | the ESC's 0% point |
| `THROTTLE_STEPS_US` | 1100, 1200, 1300, 1400, 1500, 1600 | the GUI's throttle buttons |
| `US_MAX_ALLOWED` | 1690 | hard ceiling — `set_us()` clamps everything to 1000–1690 |

### Pre-arm check

`esc_arm.power_up()` follows the order `Subcodes/Precharge.py` lays out, calling its
own functions: `INITIALIZE_SYSTEM()` → claim GPIO5/7 low → `START_PRECHARGE()` (no-op
while disabled) → `OPEN_FET()` → `TURN_OFF_PRECHARGE()` → wait `BUS_SETTLE_S` →
median INA228 bus voltage → `classify_bus_voltage()`. If the bus does not reach
`BUS_MIN_VOLTAGE` the FETs are switched off again and power-up is refused.

E-STOP / POWER OFF cut the pulses and the FETs (`CLOSE_FET()` → `CLOSE_SYSTEM()`).
**There are no running current or voltage guards** — the bus is checked once at
power-up. Stay by the battery connector.

## 2. The port: `/dev/ttyAMA10`, and turn the console off first

This uses the Pi 5's dedicated **UART debug connector** — the 3-pin JST header on the
board, which is `/dev/ttyAMA10`. That choice avoids both collisions on this hardware:

- **Confirmed on the bench:** the debug connector is `/dev/ttyAMA10` on a Pi 5
  (`/dev/ttyAMA0` is the GPIO14/15 UART). The Body test also uses this connector,
  so only one of the two can be plugged in at a time.
- the spare GPIO UART overlays (`dtoverlay=uart2`/`uart3`) put RX on **GPIO5 and
  GPIO7 — the testbox's BOT and TOP throttle outputs**. The debug connector is not on
  the GPIO header at all, so nothing is shared.

**The one setup step.** On a Pi 5 the serial console normally owns this port: it holds
the tty open and transmits boot and login chatter on it. Disable it, or captures will
either fail to open the port or be full of console text:

```bash
sudo systemctl disable --now serial-getty@ttyAMA10.service
```

and check `/boot/firmware/cmdline.txt` has no `console=ttyAMA10,...` or
`console=serial0,...` on it. `enable_uart=1` should be in `config.txt` — it already is
on this build. Reboot, then:

```bash
ls -l /dev/serial* /dev/ttyAMA*          # /dev/ttyAMA10 should be there
sudo fuser -v /dev/ttyAMA10               # should print nothing holding it
```

Add yourself to the `dialout` group if you get a permission error:
`sudo usermod -aG dialout $USER`, then log out and back in.

> A USB–TTL adapter (`/dev/ttyUSB0`) is an equally valid alternative and leaves the
> debug connector free for its actual job. Everything here takes `-p`, so either works.

Only dependency for the read-only tools is pyserial:
`pip3 install pyserial --break-system-packages`. `--control` and `esc_capture.py` also
need `lgpio` and `smbus2` (already on the test box).

## 3. The frame format

Confirmed on the bench (`esc_protocol.py`):

- **19200 baud 8N1**
- **24-byte frames**: header `0x9B`, length byte `0x16`, 20 bytes of fields, then a
  **sum16 checksum, little-endian** — the decoder rejects frames that fail it
- field **offsets and sizes** confirmed by structure (sequence counter, requested and
  output throttle, eRPM, voltage, current, phase current, two thermistors, status)

Still to calibrate: the **scale factors** in `SCALES` (see "Known-unverified" below).
`esc_sniff.py` does that without trusting the spec:

```bash
# is anything arriving, and at what baud?
python3 esc_test/esc_sniff.py --sweep

# capture at a steady throttle and analyse
python3 esc_test/esc_sniff.py -t 10 --save idle.bin
python3 esc_test/esc_sniff.py -t 10 --save spin50.bin

# re-analyse offline, as often as you like, on any machine
python3 esc_test/esc_sniff.py --analyze spin50.bin

# pin scale factors against a reading you trust (multimeter / INA228)
python3 esc_test/esc_sniff.py --analyze spin50.bin \
        --calibrate-volts 25.2 --calibrate-amps 18.4
```

The report gives the frame length and header, a byte-column table (constant /
counting / varying columns — compare idle and spinning captures), which checksum
candidate closes on every frame, and a decode preview with the current spec.

## 4. Live logging in a terminal

```bash
# the normal case: one ESC on /dev/ttyAMA10, logging to esc_test/logs/
python3 esc_test/esc_monitor.py

# named, and stop after 60 s
python3 esc_test/esc_monitor.py -p top=/dev/ttyAMA10 -t 60

# two at once, if you ever add a second UART or a USB-TTL adapter
python3 esc_test/esc_monitor.py -p top=/dev/ttyAMA10 -p bot=/dev/ttyUSB0
```

```
top   49.2 Hz  12345 eRPM   2647 rpm   25.14 V   18.42 A    463 W
      mos 42.1C cap 31.0C  thr 50.2%  phase 21.10A  | frames 1482 resync 0 crc ok
```

`frames` / `resync` / `crc` are link quality. Steady resyncs or CRC failures mean
bytes are being dropped — worth knowing before trusting the numbers.

Ctrl-C flushes the log and prints peak current, peak RPM, the voltage range and peak
temperatures.

| flag | |
|---|---|
| `-p [name=]dev` | serial port, repeatable for several ESCs |
| `-b, --baud` | default 19200 |
| `--poles N` | magnet poles, for eRPM → RPM (`rpm = eRPM / (poles/2)`). Default **4** (`DEFAULT_POLES`, set from bench RPM checks — see "Known-unverified"). `--poles 0` logs eRPM only |
| `-t, --duration` | seconds, else until Ctrl-C |
| `--hz` | screen refresh (default 5). **Logging is always at full frame rate** |
| `--csv FILE` / `--no-csv` | log elsewhere, or not at all |
| `--plain` | scrolling output, for piping into `tee` |

## 5. On the touchscreen — `esc_gui.py`

A finger-driven page for the 800×480 screen: current and RPM in 54 pt, voltage /
power / eRPM / throttle / phase current / temperatures / status underneath,
START / STOP / RESET PEAKS / CLOSE, and the link-quality counters on screen so you
can tell "0 A because it's idle" from "0 A because nothing is decoding".

```bash
python3 esc_test/esc_gui.py                      # read-only
python3 esc_test/esc_gui.py --control            # + power, arm, throttle, sweep
python3 esc_test/esc_gui.py --control -c bot     # throttle starts on GPIO5
python3 esc_test/esc_gui.py --windowed           # for a desktop
python3 esc_test/esc_gui.py --autostart          # start reading immediately
```

### With `--control`

A control strip appears:

- **POWER ON** — starts telemetry (if not already running) then runs the pre-arm check.
- **ARM** — holds 1000 µs for 2 s on both channels, then idles at 1080 µs.
- **DISARM** / **POWER OFF** — pulses off / pulses and FETs off.
- **SWEEP** — the timed sweep below.
- **E-STOP** — runs inline on the Tk thread (never queued behind a worker): pulses
  off, FETs off, fault latched on screen.
- **GPIO7 (TOP) / GPIO5 (BOT)** — which channel the throttle drives. Both are armed
  together; switching parks the old one at idle.
- **Throttle step buttons: 1100, 1200, 1300, 1400, 1500, 1600 µs.** One press = one
  write to the selected channel. The active step is highlighted and the commanded
  value shown at the right; 1100 µs (the 0% point) is the "no drive" step. The
  buttons are dead until the ESC is armed, and while a sweep is running.

### SWEEP and spin-down timing

The sweep steps the selected channel through `esc_arm.SWEEP_PROFILE`:

| phase | µs | hold |
|---|---|---|
| idle | 1080 | 2 s |
| | 1200 | 2 s |
| | 1300 | 2 s |
| | 1400 | 2 s |
| | 1500 | 2 s |
| idle | 1080 | 3 s |

then **cuts the signal** (ESC disarmed — press ARM before the next sweep). The FETs
stay on, so telemetry keeps streaming and **logging carries on past the end of the
sweep**.

The **spin-down timer starts the moment the final idle phase begins** (the drop from
1500 µs) and stops at the first telemetry frame reporting 0 eRPM
(`SPINDOWN_STOP_ERPM` in `esc_gui.py` — raise it if the ESC reports a small non-zero
eRPM at standstill). The status reads `IDLE - spinning down …` during the final idle,
`SIGNAL OFF - spinning down …` if the motor is still turning after the cut, then
`STOPPED in 4.31 s from 1497 rpm`. The result is also printed to the console and
written to `spindown_s` on that CSV row. If no 0 eRPM frame arrives within
`SPINDOWN_TIMEOUT_S` (120 s) the page says so. E-STOP or DISARM during the sweep
aborts it and discards the timer.

`cmd_us` in the log carries the sweep step being transmitted, then `0` from the cut
until the motor is seen stopped.

To change the profile, edit `SWEEP_PROFILE` in `esc_arm.py` — the on-screen
description follows it. The last phase must be idle (asserted at import), and
nothing may exceed `US_MAX_ALLOWED`.

### Safety behaviour

Blocking calls (`power_up`, `arm`, the sweep) run on worker threads so E-STOP never
waits on them; throttle and sweep are dead until the ESC is actually armed; a fault
stays on screen until POWER ON is pressed again; and closing the page (CLOSE, Escape or
the window manager) powers the arm down unconditionally.

**It runs as its own process.** The test box launches it with `subprocess.Popen` and
nothing else — no import, no shared globals. If this page throws or wedges on a port
that never answers, `MasterUI.py` is not in the traceback.

### Adding it to the test box menu

MasterUI runs fullscreen at boot, so it needs a button. In `GUI/MasterUI.py`, next to
the other page handlers:

```python
import subprocess

def esc_telemetry():
    """Launch the ESC telemetry page as a SEPARATE PROCESS (owns a serial
    port and, with --control, the arm). Drop --control for read-only."""
    path = os.path.join(os.path.dirname(__file__), "..", "esc_test", "esc_gui.py")
    subprocess.Popen([sys.executable, os.path.abspath(path), "--control"])
```

and one button in the BUILD TESTING column:

```python
b10 = ttk.Button(menu_build, text="ESC Telemetry", bootstyle=PRIMARY,
                 style="Nav.TButton", width=22, command=esc_telemetry)
b10.pack(pady=3)
```

> **Power the arm from one place only.** If MasterUI has the arm powered on another
> page, power it off there before using `--control` here. `esc_arm.power_up()` checks
> the FET and GPIO5/7 claims and refuses with a message saying so.

## 6. Scripted capture — `esc_capture.py`

Runs a capture unattended: telemetry first, pre-arm check (§1), a no-pulse hold, arm,
then a list of commanded pulse widths, logging telemetry plus the raw bytes, and PWM
off / FETs off at the end — including on Ctrl-C, SIGTERM and exceptions.

```bash
# structural capture - NOTHING TURNS (1080 us, below the 1100 us 0% point)
python3 esc_test/esc_capture.py

# with rotation: 1080, 1150, 1200, 1310, 1080
python3 esc_test/esc_capture.py --spin

python3 esc_test/esc_capture.py --steps 1080,1150,1200 --hold 8 -c bot
```

| flag | |
|---|---|
| `-c top\|bot` | throttle line, GPIO7 or GPIO5 (default top) |
| `--hold S` | seconds per phase (default 10) |
| `--steps a,b,c` | custom pulse widths (clamped to 1000–1690 µs) |
| `--spin` | use the spinning step list |
| `--out DIR` | output directory (default `esc_test/logs/`) |
| `-p`, `-b`, `--poles` | as for `esc_monitor.py` |

Writes `capture_YYYYmmdd_HHMMSS.csv` and `.bin`; feed the `.bin` to
`esc_sniff.py --analyze`. Each row carries `cmd_us`.

## 7. The log

One row per decoded frame, in `esc_test/logs/esc_YYYYmmdd_HHMMSS.csv` (GUI and
monitor), flushed every row so a run that ends badly still has its last second.
Columns:

`iso, t_s, cmd_us, spindown_s,` then the ESC's own scaled figures — `throttle_req_pct,
throttle_pct, erpm, rpm, volts, amps, phase_amps, watts, mos_temp_c, cap_temp_c` —
then every raw field except `version_raw`, then `crc_ok` and `raw_hex`.

**Raw counts and the whole frame hex are always logged**, so if a scale factor turns
out to be wrong, every past log can be decoded again rather than re-run on the bench.

## Known-unverified, in priority order

1. **Scale factors** — `SCALES` (voltage, current, phase current 0.1 per count;
   throttle 100/1024 % per count) are plausible defaults; calibrate (§3).
2. **Pole count / eRPM units** — the X8 8120 is 36N40P (40 poles), but
   `DEFAULT_POLES` is set to **4**, adjusted to match measured RPM on the bench. That
   implies the eRPM field is scaled (≈ units of 10 eRPM). Confirm against a
   tachometer; the fix is one value in `esc_protocol.py`.
3. **Temperature** — the two temperature bytes are thermistor readings converted
   with a generic 3950 K NTC curve. Treat `mos_temp_c` / `cap_temp_c` as indicative
   and trust the raw columns.
4. **Field meanings past the counter** — offsets are confirmed by structure; which
   column is which is from the HW-FOC protocol order and should be sanity-checked
   against a spinning capture.

## If nothing arrives

- **Is the serial console still holding `/dev/ttyAMA10`?** This is the usual answer on
  a Pi 5 — see §2. `sudo fuser -v /dev/ttyAMA10` tells you.
- Telemetry wire on the debug connector's **RX**, and a common ground?
- Is the ESC powered? The telemetry stream only exists when the ESC is up
  (with `--control`, after POWER ON).
- Is something else holding the port? The monitor opens exclusively and will say so.
  Two readers on one tty split the bytes and both see garbage.
