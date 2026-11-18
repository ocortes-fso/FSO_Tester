# ESC_Serial — Hobbywing ESC serial telemetry

Standalone live logger for current, RPM and everything else a Hobbywing X-series
ESC puts on its telemetry wire. Reads a UART, prints a live readout, writes a CSV.

**Read-only by default.** `esc_protocol`, `esc_sniff`, `esc_monitor` and `esc_gui`
without `--control` import nothing from `Subcodes/` or `GUI/`, touch no GPIO and no
I²C, and never transmit a byte to the ESC. You can leave any of them recording while
something else drives the motor.

**`esc_arm.py` is the one exception, and it is opt-in.** It can power the arm, arm the
ESC and command throttle — so that one person can run a capture end to end — and it
does all of it by calling the test box's own subcodes rather than reimplementing any
of it. `esc_capture.py` and `esc_gui.py --control` are the two things that use it.
Only one process may own the arm at a time; see §6.

```
ESC_Serial/
├── esc_protocol.py   frame spec, scale factors, checksum candidates, decoder
├── esc_sniff.py      bench tool: confirm the frame format and the scale factors
├── esc_monitor.py    live readout + CSV logger, for a terminal
├── esc_gui.py        the same thing as a touchscreen page, for the test box
├── esc_capture.py    scripted capture: powers the arm, arms, holds, logs, powers down
├── esc_arm.py        the only file that touches hardware - optional, see below
└── logs/             timestamped CSVs and raw captures (gitignored)
```

---

## 1. Wiring

The ESC telemetry line is a single 3.3 V TTL output: the ESC talks, nothing listens
back. Two wires:

| ESC | Raspberry Pi 5 |
|---|---|
| telemetry / TLM (signal out) | **RX** on the UART debug connector |
| GND | GND on the same connector |

Do **not** connect the Pi's TX to the ESC. One UART reads one ESC; to read the other
one, move the single wire across.

## 2. The port: `/dev/ttyAMA0`, and turn the console off first

This uses the Pi 5's dedicated **UART debug connector** — the 3-pin JST header on the
board, which is `/dev/ttyAMA0`. That choice avoids both collisions on this hardware:

- `/dev/ttyAMA10` (GPIO14/15) is the flight-controller MAVLink link the Body test
  uses, so it has to stay clear.
- the spare GPIO UART overlays (`dtoverlay=uart2`/`uart3`) put RX on **GPIO5 and
  GPIO7 — the testbox's BOT and TOP throttle outputs**. The debug connector is not on
  the GPIO header at all, so nothing is shared.

**The one setup step.** On a Pi 5 the serial console normally owns this port: it holds
the tty open and transmits boot and login chatter on it. Disable it, or captures will
either fail to open the port or be full of console text:

```bash
sudo systemctl disable --now serial-getty@ttyAMA0.service
```

and check `/boot/firmware/cmdline.txt` has no `console=ttyAMA0,...` or
`console=serial0,...` on it (the main README already has you removing the `serial0`
one). `enable_uart=1` should be in `config.txt` — it already is on this build. Reboot,
then:

```bash
ls -l /dev/serial* /dev/ttyAMA*          # /dev/ttyAMA0 should be there
sudo fuser -v /dev/ttyAMA0               # should print nothing holding it
```

Add yourself to the `dialout` group if you get a permission error:
`sudo usermod -aG dialout $USER`, then log out and back in.

> A USB–TTL adapter (`/dev/ttyUSB0`) is an equally valid alternative and leaves the
> debug connector free for its actual job. Everything here takes `-p`, so either works.

Only dependency is pyserial, which the testbox already uses:
`pip3 install pyserial --break-system-packages`.

## 3. Confirm the frame format — do this first

> **Can't spin a motor yet?** Run `python3 ESC_Serial/esc_capture.py` with no flags.
> It powers up, arms and holds 1080 µs — all below the ESC's 1100 µs 0% point, so
> nothing turns — and that single run still pins down the frame length, the header,
> the checksum, the sequence counter, the voltage and temperature columns, and the
> throttle columns at three distinct commanded values. Only the RPM and current
> *scale factors* need rotation.


**The frame layout in `esc_protocol.py` is a documented candidate, not a verified
fact.** Hobbywing does not publish the format and it differs between models and
firmware revisions, so the offsets and scale factors have to be confirmed against
your actual ESC once. `esc_sniff.py` does that without trusting the candidate: it
derives the frame length, the field structure and the checksum from the bytes
themselves.

```bash
# is anything arriving, and at what baud?
python3 ESC_Serial/esc_sniff.py --sweep

# capture at a steady throttle and analyse
python3 ESC_Serial/esc_sniff.py -t 10 --save idle.bin
python3 ESC_Serial/esc_sniff.py -t 10 --save spin50.bin

# re-analyse offline, as often as you like, on any machine
python3 ESC_Serial/esc_sniff.py --analyze spin50.bin
```

The report gives you four things:

- **frame length** and the header bytes → `FRAME_LEN`, `HEADER`, `LEN_BYTE`
- **a byte-column table** — which offsets are constant, which count +1 per frame (the
  sequence counter), which vary. Compare the idle and spinning captures: the columns
  that move with throttle are RPM, current and phase current → `SPEC` offsets
- **the checksum** — whichever candidate closes on every frame → `CRC_NAME`,
  `CRC_SPAN`, `CRC_ENDIAN`. Setting these makes the decoder reject corrupt frames
  instead of passing them through
- **a decode preview** using the candidate spec, to sanity-check against the bench

Then pin the scale factors against a reading you trust (multimeter, or the testbox's
own INA228 display) and put the results in `SCALES`:

```bash
python3 ESC_Serial/esc_sniff.py --analyze spin50.bin \
        --calibrate-volts 25.2 --calibrate-amps 18.4
```

## 4. Live logging

```bash
# the normal case: one ESC on /dev/ttyAMA0, X8 pole count, logging to logs/
python3 ESC_Serial/esc_monitor.py

# named, and stop after 60 s
python3 ESC_Serial/esc_monitor.py -p top=/dev/ttyAMA0 -t 60

# two at once, if you ever add a second UART or a USB-TTL adapter
python3 ESC_Serial/esc_monitor.py -p top=/dev/ttyAMA0 -p bot=/dev/ttyUSB0
```

```
top   49.2 Hz  12345 eRPM   2647 rpm   25.14 V   18.42 A    463 W
      mos 42.1C cap 31.0C  thr 50.2%  phase 21.10A  | frames 1482 resync 0 crc -
```

`frames` / `resync` / `crc` are link quality. Steady resyncs mean bytes are being
dropped or the frame spec is still wrong — worth knowing before trusting the numbers.
`crc -` means no checksum has been confirmed yet (step 3).

Ctrl-C flushes the log and prints peak current, peak RPM, the voltage range and peak
temperatures.

| flag | |
|---|---|
| `-p [name=]dev` | serial port, repeatable for several ESCs |
| `-b, --baud` | default 19200 |
| `--poles N` | magnet poles, for eRPM → RPM. Default 40 — the X8 8120 is 36N40P, so 20 pole pairs and `rpm = eRPM / 20`. `--poles 0` logs eRPM only |
| `-t, --duration` | seconds, else until Ctrl-C |
| `--hz` | screen refresh (default 5). **Logging is always at full frame rate** |
| `--csv FILE` / `--no-csv` | log elsewhere, or not at all |
| `--plain` | scrolling output, for piping into `tee` |

## 5. On the touchscreen

`esc_gui.py` is the same monitor as a finger-driven page for the 800×480 screen:
current and RPM in 54pt, the rest underneath, START / STOP / RESET PEAKS / CLOSE, and
the link-quality counters on screen so you can tell "0 A because it's idle" from "0 A
because nothing is decoding".

```bash
python3 ESC_Serial/esc_gui.py                      # read-only
python3 ESC_Serial/esc_gui.py --control            # + power, arm and throttle
python3 ESC_Serial/esc_gui.py --windowed           # for a desktop
```

With `--control` it grows a POWER ON / ARM / DISARM / POWER OFF row, a throttle slider
spanning Manual_PWM_Test's own `SLIDER_MIN_US`–`US_MAX_ALLOWED`, an E-STOP, and a
third big panel: **the shunt's current next to the ESC's own**, with their ratio. That
ratio is the calibration figure for `SCALES["current"]`, and two readings that agree
are two readings you can trust.

The page is deliberately conservative about state: the throttle slider is dead until
the ESC is actually armed, blocking calls (`power_up`, `arm`) run on worker threads so
the E-STOP never waits on them, slider drags are rate-limited to 25 Hz of hardware
writes, a guard trip escalates to a full emergency stop and stays on screen, and
closing the page powers the arm down unconditionally.

**It runs as its own process.** The test box launches it with `subprocess.Popen` and
nothing else — no import, no shared globals. If this page throws or wedges on a port
that never answers, `MasterUI.py` is not in the traceback. A page *inside* MasterUI
would have given that up: one process, one crash, and a stuck `read()` blocking the
same Tk thread that owns the emergency stop.

### Adding it to the test box menu

MasterUI runs fullscreen at boot, so a desktop shortcut is unreachable — it needs a
button. In `GUI/MasterUI.py`, next to the other page handlers:

```python
import subprocess

def esc_telemetry():
    """
    Launch the ESC telemetry page as a SEPARATE PROCESS.

    Not a page in this file on purpose: it owns a serial port and, with
    --control, the arm. Keeping it in its own process means a fault in it
    cannot reach this GUI, and the arm has exactly one owner at a time.

    Drop --control to launch it read-only, which is safe to run while this
    GUI has the arm powered.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "ESC_Serial", "esc_gui.py")
    subprocess.Popen([sys.executable, os.path.abspath(path), "--control"])
```

and one button in the BUILD TESTING column (four buttons there now; a fifth fits —
5 × 51 + 50 = 305 px against the 404 px that column has):

```python
b10 = ttk.Button(menu_build, text="ESC Telemetry", bootstyle=PRIMARY,
                 style="Nav.TButton", width=22, command=esc_telemetry)
b10.pack(pady=3)
```

> **Power the arm from one place only.** If MasterUI has the arm powered on its
> Prop TEST V2 or Cv2_A06 page, press POWER OFF there before using `--control` here.
> `esc_arm.power_up()` checks and refuses with a message saying exactly that, so the
> failure is a message rather than two processes commanding one FET.

## 6. Running a capture on your own

`esc_capture.py` does the whole thing unattended: powers the arm, arms the ESC, walks
a list of commanded pulse widths, logs the ESC telemetry next to the INA228 reading,
saves the raw bytes, and powers down — including on Ctrl-C, on a guard trip, and on an
exception.

```bash
# structural capture - NOTHING TURNS (stops at 1080 us, below the 1100 us 0% point)
python3 ESC_Serial/esc_capture.py

# with rotation, once a motor can be turned
python3 ESC_Serial/esc_capture.py --spin

python3 ESC_Serial/esc_capture.py --steps 1080,1150,1200 --hold 8 -c bot
```

Every call goes through `esc_arm.py` to the test box's own subcodes, in their order:

| | |
|---|---|
| `Precharge.INITIALIZE_SYSTEM()` / `CLOSE_FET()` | claim the gpiochip, FET de-energised |
| `Hobbywing_Prop_Test.session_power_up()` | close the FETs, **verify the bus came up**, arm the over-current / under-voltage guards, start the INA228 sampler and its own CSV in `Logs/` |
| `Manual_PWM_Test.arm()` | hold 1000 µs so the ESC will arm, settle at 1080 µs |
| `Manual_PWM_Test.set_channel()` | clamped to 1080–1400 µs |
| `Manual_PWM_Test.disarm()` → `session_power_off()` → `session_stop_monitor()` → `Precharge.CLOSE_SYSTEM()` | teardown, in `finally` |

So the throttle ceiling, the arming sequence and the guards are whatever those modules
say they are — nothing here duplicates or can exceed them, and nothing here needs
changing when they change.

Each row carries `phase`, `cmd_us`, `shunt_volts` and `shunt_amps` alongside the ESC's
own figures, so the analysis can slice by phase and compare the two current
measurements directly.

## 7. The log

One row per decoded frame, in `logs/esc_YYYYmmdd_HHMMSS.csv`, flushed every row so a
run that ends badly still has its last second. Columns:

`iso, t_s, esc, phase, cmd_us, shunt_volts, shunt_amps,` then the ESC's own scaled
figures — `throttle_req_pct, throttle_pct, erpm, rpm, volts, amps, phase_amps, watts,
mos_temp_c, cap_temp_c` — then every raw field, then `crc_ok` and `raw_hex`.

**Raw counts and the whole frame hex are always logged.** That is deliberate: if a
scale factor or a field offset turns out to be wrong, every past log can be decoded
again rather than re-run on the bench.

## Known-unverified, in priority order

1. **Field offsets** — candidate layout, confirm with `esc_sniff.py` (§3).
2. **Checksum** — `CRC_NAME = None` until the sniffer identifies it. Until then
   frames are accepted on header + length byte alone.
3. **Scale factors** — `SCALES` are plausible defaults; calibrate (§3).
4. **Temperature** — the two temperature bytes are thermistor readings, converted
   with a generic 3950 K NTC curve. The series resistor and ADC reference on this ESC
   are unverified, so treat `mos_temp_c` / `cap_temp_c` as indicative and trust the
   raw columns. Confirm with a heat gun and a contact probe.
5. **eRPM units** — the pole count (40, from 36N40P) is known, but whether the field
   is plain eRPM or eRPM in units of 10 is not. An 8120 on 6S tops out around
   2,000–3,000 rpm, i.e. 40,000–60,000 eRPM, which only just fits a 16-bit field — so
   if the RPM column reads about 10× low at full throttle, that field is scaled and
   the fix is one entry in `SCALES`. §3's spinning capture settles it.

## If nothing arrives

- **Is the serial console still holding `/dev/ttyAMA0`?** This is the usual answer on
  a Pi 5 — see §2. `sudo fuser -v /dev/ttyAMA0` tells you.
- Telemetry wire on the debug connector's **RX**, and a common ground?
- Is the ESC powered? The telemetry stream only exists when the ESC is up.
- Is something else holding the port? The monitor opens exclusively and will say so.
  Two readers on one tty split the bytes and both see garbage.
