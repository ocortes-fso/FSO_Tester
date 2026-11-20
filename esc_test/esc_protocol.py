#!/usr/bin/env python3
"""
Hobbywing X-series ESC serial telemetry - frame spec, CRC candidates, decoder.

STANDALONE BY DESIGN
--------------------
Nothing in ESC_Serial/ imports from Subcodes/ or GUI/, and nothing in the
testbox imports from here. This module touches no GPIO, no I2C, no gpiochip,
and never writes a byte to the serial port - it is a listener. Running it
cannot disturb a test box build, and it does not need the GUI stopped unless
you are stealing a port the GUI already holds (it will not: the ESC telemetry
port is a different device - see README.md).

THE FRAME SPEC IS A CANDIDATE, NOT A FACT
-----------------------------------------
The Hobbywing X-series telemetry stream is not publicly specified, and the
field offsets and scale factors differ between models and firmware. What is in
SPEC below is the widely-reported X6/X8/X9/X11 layout: a 22-byte frame opening
0x9B 0x16, carrying a sequence counter, requested and actual throttle, eRPM,
voltage, phase current, bus current, two thermistor readings, a status word and
a 2-byte checksum.

Treat it as a hypothesis to be confirmed on the bench. esc_sniff.py works out
the real frame length, which byte columns move, and which checksum actually
closes - WITHOUT using this spec - so you can correct it from a measured
capture instead of trusting it. Everything correctable lives in SPEC and
SCALES; nothing else in this package hard-codes an offset.

Raw integers are always carried alongside the scaled values, in the live
readout and in the CSV, so a scale factor that turns out to be wrong can be
re-derived from an old log rather than needing a new capture.
"""

from __future__ import annotations

import struct
from collections import namedtuple

# ---------------------------------------------------------------------------
# Frame spec - CANDIDATE, confirm with esc_sniff.py
# ---------------------------------------------------------------------------

HEADER = 0x9B           # first byte of every frame
LEN_BYTE = 0x16         # second byte: 22 = everything before the checksum
FRAME_LEN = 24          # 22 + 2-byte checksum. CONFIRMED on the bench.

# 19200 8N1 - CONFIRMED on the bench (Pi 5 debug connector, ESC spinning).
DEFAULT_BAUD = 19200

# /dev/ttyAMA10 is the Pi 5's 3-pin JST UART debug connector (CONFIRMED - the
# ESC frames arrive there). /dev/ttyAMA0 is the GPIO14/15 UART, not this one.
# The Body test also uses this connector, so the two tests cannot share it at
# the same time - unplug one before the other.
#
# ONE SETUP STEP: the serial console usually owns this port. It has to be off
# or it holds the tty and transmits on it. See README.md section 2.
DEFAULT_PORT = "/dev/ttyAMA10"

# A field is (name, offset, size, signed). Offsets are from the header byte.
# Multi-byte integers are big-endian unless the name ends in "_le".
Field = namedtuple("Field", "name offset size signed")

# Layout from a bench capture (24-byte frames, sum16 checksum closes on every
# frame) and the HW-FOC protocol order. Example frame, motor at low throttle:
#   9b 16 01 02 | 11 8b | 00 73 | 00 73 | 01 a4 | 00 e4 | 00 04 | 00 2f | cf | d2 | 00 00 | 93 05
#   hdr len ver cmd  seq   thr_in  thr_out  rpm    volts   amps   phase   mos  cap  status  sum16 LE
# Offsets/sizes: CONFIRMED by structure. Field meanings past the counter and
# the scale factors: still to calibrate (multimeter / tachometer).
SPEC = (
    Field("version_raw", 2, 1, False),       # 0x01
    Field("cmd_raw", 3, 1, False),           # 0x02 = real-time data
    Field("counter", 4, 2, False),           # +1 per frame
    Field("throttle_req_raw", 6, 2, False),  # throttle input
    Field("throttle_raw", 8, 2, False),      # throttle output
    Field("erpm_raw", 10, 2, False),
    Field("voltage_raw", 12, 2, False),      # 0x00e4 = 228 -> 22.8 V on 6S
    Field("current_raw", 14, 2, True),       # bus / battery current
    Field("phase_current_raw", 16, 2, True),  # motor phase current
    Field("mos_temp_raw", 18, 1, False),      # FET thermistor
    Field("cap_temp_raw", 19, 1, False),      # capacitor thermistor
    Field("status_raw", 20, 2, False),        # fault / status bits
    Field("crc_raw", 22, 2, False),           # stored little-endian
)

CRC_FIELD = "crc_raw"

# ---------------------------------------------------------------------------
# Scale factors - CANDIDATE, calibrate with esc_sniff.py --calibrate
# ---------------------------------------------------------------------------
# Each is "engineering units per raw count". The sniffer's --calibrate mode
# prints raw/known ratios against a reading you take with a multimeter or off
# the testbox INA228, which is how these get pinned down.
SCALES = {
    "voltage": 0.1,          # V per count
    "current": 0.1,          # A per count
    "phase_current": 0.1,    # A per count
    "throttle": 100.0 / 1024,  # percent per count - UNVERIFIED (0-1024?)
}

# eRPM -> mechanical RPM needs the motor's magnet POLE count (not the stator
# slot count):
#     rpm = erpm / (poles / 2)
#
# The Hobbywing X8 motor (8120) is 36N40P: 36 stator slots, 40 magnet poles.
# 40 poles = 20 pole pairs, so mechanical RPM is eRPM / 20.
#
# Set --poles 0 to turn the conversion off, in which case the rpm column is
# left empty rather than filled with a number nobody checked.
DEFAULT_POLES = 4       # X8 / 8120, 36N40P


def mech_rpm(erpm, poles=DEFAULT_POLES):
    """
    Mechanical RPM from electrical RPM, or None if the pole count is unset.

    poles is the magnet count: the "40" in 36N40P, not the "36".
    """
    if not poles or erpm is None:
        return None
    return erpm / (poles / 2.0)


# ---------------------------------------------------------------------------
# Temperature
# ---------------------------------------------------------------------------
# The two temperature bytes are a thermistor reading, not degrees. The mapping
# below is a 25 degC / 3950 K NTC divider, which is the usual arrangement, but
# the series resistor and ADC reference are unverified on this ESC - so the
# raw byte is ALWAYS logged and this is clearly a derived column. If the number
# looks wrong, fix it here; no capture is lost.
_NTC_BETA = 3950.0
_NTC_T0_K = 298.15      # 25 degC
_NTC_FULL_SCALE = 255.0


def temp_from_raw(raw):
    """
    Best-effort degC from a thermistor byte. None if out of range.

    Deliberately simple and deliberately suspect. Confirm by warming the ESC
    with a heat gun and watching raw vs. a contact probe before you trust the
    degC column for anything that matters.
    """
    if raw is None or raw <= 0 or raw >= _NTC_FULL_SCALE:
        return None
    import math
    ratio = raw / (_NTC_FULL_SCALE - raw)
    try:
        t_k = 1.0 / (1.0 / _NTC_T0_K + (1.0 / _NTC_BETA) * math.log(ratio))
    except (ValueError, ZeroDivisionError):
        return None
    return t_k - 273.15


# ---------------------------------------------------------------------------
# Checksum candidates
# ---------------------------------------------------------------------------
# Which checksum the ESC uses is one of the things to confirm, so every
# plausible one is implemented and esc_sniff.py tries all of them against real
# frames. Once one closes on hundreds of frames, set CRC_NAME to it and the
# decoder starts rejecting corrupt frames instead of passing them through.


def crc8_sum(data):
    return sum(data) & 0xFF


def crc8_xor(data):
    v = 0
    for b in data:
        v ^= b
    return v


def crc16_sum(data):
    return sum(data) & 0xFFFF


def crc16_modbus(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def crc16_arc(data):
    crc = 0x0000
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def crc16_ccitt_false(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def crc16_xmodem(data):
    crc = 0x0000
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


CRC_FUNCS = {
    "sum8": (crc8_sum, 1),
    "xor8": (crc8_xor, 1),
    "sum16": (crc16_sum, 2),
    "modbus16": (crc16_modbus, 2),
    "arc16": (crc16_arc, 2),
    "ccitt16": (crc16_ccitt_false, 2),
    "xmodem16": (crc16_xmodem, 2),
}

# None = "unconfirmed, do not check". Set this to a key of CRC_FUNCS once
# esc_sniff.py tells you which one matches, together with CRC_SPAN and
# CRC_ENDIAN from the same report.
# CONFIRMED: 16-bit sum of bytes 0..21, stored little-endian at 22..23.
CRC_NAME = "sum16"
CRC_SPAN = (0, FRAME_LEN - 2)    # byte range the checksum covers
CRC_ENDIAN = "little"            # how the checksum itself is stored


def _read_int(buf, field):
    """Pull one spec field out of a frame buffer."""
    end = field.offset + field.size
    if end > len(buf):
        return None
    chunk = buf[field.offset:end]
    value = int.from_bytes(chunk, "big", signed=False)
    if field.signed and chunk[0] & 0x80:
        value -= 1 << (8 * field.size)
    return value


def crc_ok(buf):
    """
    True / False / None - None meaning "no confirmed checksum to check".

    Returning None rather than True for the unconfirmed case keeps the
    distinction visible: the live readout shows "crc: unchecked" instead of
    claiming frames passed a test that never ran.
    """
    if CRC_NAME is None:
        return None
    func, width = CRC_FUNCS[CRC_NAME]
    lo, hi = CRC_SPAN
    want = int.from_bytes(buf[hi:hi + width], CRC_ENDIAN, signed=False)
    return func(buf[lo:hi]) == want


def decode(buf, poles=DEFAULT_POLES):
    """
    Decode one frame into a flat dict of raw and scaled values.

    Raw first, scaled second, and the raw keys are never dropped: every number
    in the CSV can be re-derived if a scale factor changes.
    """
    out = {f.name: _read_int(buf, f) for f in SPEC}

    v = out.get("voltage_raw")
    i = out.get("current_raw")
    pi = out.get("phase_current_raw")

    out["volts"] = None if v is None else v * SCALES["voltage"]
    out["amps"] = None if i is None else i * SCALES["current"]
    out["phase_amps"] = None if pi is None else pi * SCALES["phase_current"]
    out["watts"] = (
        None if (out["volts"] is None or out["amps"] is None)
        else out["volts"] * out["amps"]
    )

    thr = out.get("throttle_raw")
    thr_req = out.get("throttle_req_raw")
    out["throttle_pct"] = None if thr is None else thr * SCALES["throttle"]
    out["throttle_req_pct"] = None if thr_req is None else thr_req * SCALES["throttle"]

    out["erpm"] = out.get("erpm_raw")
    out["rpm"] = mech_rpm(out["erpm"], poles)

    out["mos_temp_c"] = temp_from_raw(out.get("mos_temp_raw"))
    out["cap_temp_c"] = temp_from_raw(out.get("cap_temp_raw"))

    out["crc_ok"] = crc_ok(buf)
    return out


# Order the CSV and the live readout use. Raw columns last so the interesting
# ones are on the left when you open the file.
SCALED_KEYS = (
    "throttle_req_pct", "throttle_pct", "erpm", "rpm",
    "volts", "amps", "phase_amps", "watts", "mos_temp_c", "cap_temp_c",
)
RAW_KEYS = tuple(f.name for f in SPEC)


class FrameReader:
    """
    Byte stream -> frames, with resynchronisation.

    Feed it whatever read() returned; it yields complete frames. A serial
    stream that is joined mid-frame, or that drops bytes, has to be re-aligned
    rather than read at a fixed stride, so a frame is only accepted when both
    the header byte AND the length byte are where they should be (and the
    checksum too, once one is confirmed). Anything else advances one byte and
    tries again, which is the only resync that cannot lock onto an offset.

    Counters are kept so the live readout can show link quality instead of
    silently dropping bad data: frames, resyncs (bytes thrown away) and
    crc_fails.
    """

    def __init__(self, header=HEADER, len_byte=LEN_BYTE, frame_len=FRAME_LEN,
                 check_crc=True):
        self.header = header
        self.len_byte = len_byte
        self.frame_len = frame_len
        self.check_crc = check_crc
        self._buf = bytearray()
        self.frames = 0
        self.resyncs = 0
        self.crc_fails = 0

    def feed(self, data):
        """Append bytes, yield every complete frame now available."""
        self._buf += data
        while True:
            frame = self._next()
            if frame is None:
                return
            yield frame

    def _next(self):
        buf = self._buf
        while True:
            start = buf.find(self.header)
            if start < 0:
                # No header anywhere. Keep nothing: a stray partial header can
                # only be at the very end, so hold the last byte back.
                if buf:
                    self.resyncs += len(buf) - 1
                    del buf[:-1]
                return None
            if start:
                self.resyncs += start
                del buf[:start]
            if len(buf) < self.frame_len:
                return None

            # Length byte is the cheap structural check. It is what stops a
            # 0x9B that happens to appear inside a payload from being taken
            # for a frame start.
            if self.len_byte is not None and buf[1] != self.len_byte:
                self.resyncs += 1
                del buf[:1]
                continue

            frame = bytes(buf[:self.frame_len])

            if self.check_crc and CRC_NAME is not None and not crc_ok(frame):
                self.crc_fails += 1
                self.resyncs += 1
                del buf[:1]
                continue

            del buf[:self.frame_len]
            self.frames += 1
            return frame

    def stats(self):
        return {"frames": self.frames, "resyncs": self.resyncs,
                "crc_fails": self.crc_fails}
