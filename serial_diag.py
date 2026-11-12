#!/usr/bin/env python3
"""
FSO_Tester - serial link diagnostic for the Body Serial test.

Run on the Raspberry Pi 5 with the UART JST connected to the board under test:
    python3 serial_diag.py                # default /dev/ttyAMA10
    python3 serial_diag.py /dev/ttyAMA10  # explicit port

Stop the GUI (MasterUI.py) first so it is not holding the port.

What it does:
  1. Checks the port exists and nothing else has it open.
  2. Listens raw at 57600 for 3 s and reports byte count + MAVLink start bytes.
  3. If nothing useful at 57600, sweeps common baud rates.
  4. Tries a real pymavlink heartbeat at the best baud found.
"""
import os
import subprocess
import sys
import time

import serial
from pymavlink import mavutil

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyAMA10"
EXPECTED_BAUD = 57600
BAUDS = [57600, 115200, 921600, 38400, 19200, 9600, 230400, 460800, 500000]
LISTEN_S = 3.0


def header(t):
    print("\n" + "=" * 60 + f"\n{t}\n" + "=" * 60)


def check_port():
    header(f"1) Port check: {PORT}")
    if not os.path.exists(PORT):
        print("FAIL: port does not exist. Check `ls -l /dev/ttyAMA* /dev/serial*`.")
        sys.exit(1)
    print("OK: port exists")
    try:
        out = subprocess.run(["fuser", "-v", PORT], capture_output=True, text=True)
        users = (out.stdout + out.stderr).strip()
        if users and PORT in users and len(users.splitlines()) > 1:
            print("WARNING: something else has the port open:\n" + users)
        else:
            print("OK: no other process holds the port")
    except FileNotFoundError:
        print("(fuser not installed - skip; `sudo apt install psmisc` to enable)")


def listen(baud):
    """Return (byte_count, n_fd, n_fe, sample_bytes)."""
    with serial.Serial(PORT, baud, timeout=0.1) as s:
        s.reset_input_buffer()
        data = bytearray()
        t0 = time.time()
        while time.time() - t0 < LISTEN_S:
            data += s.read(4096)
    return len(data), data.count(0xFD), data.count(0xFE), bytes(data[:48])


def raw_listen():
    header(f"2) Raw listen at {EXPECTED_BAUD} for {LISTEN_S:.0f}s")
    n, fd, fe, sample = listen(EXPECTED_BAUD)
    print(f"bytes={n}  0xFD(MAVLink2)={fd}  0xFE(MAVLink1)={fe}")
    if sample:
        print("first bytes:", sample.hex(" "))
    if n == 0:
        print("-> NOTHING received. Wiring / TX-RX swap / no power / port not "
              "transmitting on the autopilot. See guide sections C and D.")
    elif fd + fe == 0:
        print("-> Bytes arrive but no MAVLink start bytes: baud mismatch, wrong "
              "protocol on that port, or signal-level/inversion problem.")
    else:
        print("-> MAVLink-looking traffic present at the expected baud.")
    return n, fd + fe


def sweep():
    header("3) Baud sweep")
    best = None
    for b in BAUDS:
        try:
            n, fd, fe, _ = listen(b)
        except serial.SerialException as e:
            print(f"{b:>7}: error {e}")
            continue
        score = fd + fe
        print(f"{b:>7}: bytes={n:<6} mavlink_start_bytes={score}")
        if score and (best is None or score > best[1]):
            best = (b, score)
    if best:
        print(f"-> Most MAVLink-like traffic at {best[0]} baud")
        if best[0] != EXPECTED_BAUD:
            print(f"   The board's SERIALx_BAUD does not match the tester "
                  f"({EXPECTED_BAUD}). Fix the parameter on the board.")
        return best[0]
    print("-> No MAVLink traffic at any baud.")
    return None


def heartbeat(baud):
    header(f"4) pymavlink heartbeat at {baud}")
    m = mavutil.mavlink_connection(PORT, baud=baud)
    try:
        hb = m.wait_heartbeat(timeout=10)
        if hb:
            print(f"PASS: heartbeat sys={m.target_system} comp={m.target_component} "
                  f"type={hb.type} autopilot={hb.autopilot}")
            return True
        print("FAIL: no heartbeat in 10 s")
        return False
    finally:
        m.close()


if __name__ == "__main__":
    check_port()
    n, mav = raw_listen()
    baud = EXPECTED_BAUD if mav else sweep()
    if baud:
        heartbeat(baud)
