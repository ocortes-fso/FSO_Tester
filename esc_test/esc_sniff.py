#!/usr/bin/env python3
"""
esc_sniff.py - work out what the ESC is actually sending.

This is the tool that turns the candidate spec in esc_protocol.py into a
confirmed one. It deliberately does NOT use that spec to find frames: it
discovers the frame length from the byte stream itself, so it cannot confirm
its own assumption. Read-only on the port, writes nothing to the ESC.

TYPICAL BENCH SESSION
---------------------
    # 1. is anything arriving at all, and at what baud?
    python3 ESC_Serial/esc_sniff.py --sweep

    # 2. capture 10 s with the motor at a steady, known throttle and
    #    analyse the structure. Saves the raw bytes too.
    python3 ESC_Serial/esc_sniff.py -p /dev/ttyAMA2 -t 10 --save idle.bin

    # 3. same again while spinning, so the columns that track RPM and
    #    current can be told apart from the ones that do not move
    python3 ESC_Serial/esc_sniff.py -t 10 --save spin50.bin

    # 4. re-analyse a capture offline, as often as you like, anywhere
    python3 ESC_Serial/esc_sniff.py --analyze spin50.bin

    # 5. pin the scale factors against a meter reading
    python3 ESC_Serial/esc_sniff.py --analyze spin50.bin \
            --calibrate-volts 25.2 --calibrate-amps 18.4

WHAT THE REPORT TELLS YOU
-------------------------
  frame length      -> FRAME_LEN, and the header/length bytes
  column table      -> which offsets are constant (candidates for header,
                       reserved and status), which increment once per frame
                       (the sequence counter), and which vary (the measurands)
  checksum          -> which of the candidate CRCs closes over which byte
                       range; set CRC_NAME / CRC_SPAN / CRC_ENDIAN from this
  decode preview    -> the candidate spec applied to real frames, so the
                       numbers can be sanity-checked against the bench
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import esc_protocol as proto

try:
    import serial
except ImportError:
    serial = None

SWEEP_BAUDS = [19200, 115200, 57600, 9600, 38400, 230400, 250000, 460800, 921600]


def header(text):
    print("\n" + "=" * 68)
    print(text)
    print("=" * 68)


def need_serial():
    if serial is None:
        sys.exit("pyserial is not installed. `pip3 install pyserial` "
                 "(add --break-system-packages on Raspberry Pi OS).")


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def capture(port, baud, seconds):
    """Listen for `seconds` and return the raw bytes. Never transmits."""
    need_serial()
    data = bytearray()
    # exclusive=True so we fail loudly if something else already holds the
    # port, rather than quietly splitting the byte stream with it - two
    # readers on one tty each get half the bytes and both see garbage.
    with serial.Serial(port, baud, timeout=0.1, exclusive=True) as s:
        s.reset_input_buffer()
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds:
            data += s.read(4096)
    return bytes(data)


def sweep(port, seconds):
    header(f"Baud sweep on {port}, {seconds:.1f}s each")
    print("Looking for a baud where the bytes show a repeating structure.\n")
    results = []
    for baud in SWEEP_BAUDS:
        try:
            data = capture(port, baud, seconds)
        except Exception as e:          # noqa: BLE001 - report and keep going
            print(f"{baud:>7}: error {e}")
            continue
        rate = len(data) / seconds
        best = best_period(data)
        note = ""
        if best:
            period, score = best
            note = f"period={period}B score={score:.2f}"
        print(f"{baud:>7}: {len(data):>6} bytes  {rate:>8.0f} B/s  {note}")
        if best:
            results.append((best[1], baud, best[0], len(data)))

    if not results:
        print("\nNo structured traffic at any baud. Things to check, in order:")
        print("  * is the ESC powered, and is it the serial-telemetry variant")
        print("    rather than the CAN one?")
        print("  * telemetry wire to the Pi's RX pin, and a common ground")
        print("  * is the UART enabled and is this the right /dev node?")
        print("    `ls -l /dev/serial* /dev/ttyAMA*`")
        return None

    results.sort(reverse=True)
    score, baud, period, nbytes = results[0]
    print(f"\n-> Best: {baud} baud, repeating every {period} bytes "
          f"(score {score:.2f})")
    if baud != proto.DEFAULT_BAUD:
        print(f"   NOTE: esc_protocol.DEFAULT_BAUD is {proto.DEFAULT_BAUD}. "
              f"Update it, or always pass --baud {baud}.")
    return baud


# ---------------------------------------------------------------------------
# Structure discovery
# ---------------------------------------------------------------------------

def best_period(data, min_len=6, max_len=96):
    """
    Infer the frame length without assuming anything about the content.

    Every byte value that appears often enough to be a frame marker is tested:
    if the gaps between its occurrences are dominated by one value, that gap is
    the frame length and the fraction of gaps agreeing is the score. A real
    framed protocol scores near 1.0; noise scores low and scattered.

    Returns (period, score) or None.
    """
    if len(data) < min_len * 4:
        return None

    counts = Counter(data)
    best = None
    # Only values common enough to plausibly be one-per-frame.
    for value, n in counts.most_common(24):
        if n < 4:
            continue
        positions = [i for i, b in enumerate(data) if b == value]
        gaps = Counter(b - a for a, b in zip(positions, positions[1:]))
        for gap, gap_n in gaps.most_common(3):
            if not (min_len <= gap <= max_len):
                continue
            score = gap_n / max(1, len(positions) - 1)
            # Prefer a high score; break ties toward the longer period, since
            # a true frame length's divisors can also score well.
            key = (round(score, 3), gap)
            if score >= 0.5 and (best is None or key > best[0]):
                best = (key, (gap, score, value))
    if best is None:
        return None
    gap, score, _value = best[1]
    return gap, score


def rotations(data, period):
    """
    Every possible alignment of the stream into `period`-byte frames.

    All `period` rotations are kept rather than one being picked here, because
    constancy alone CANNOT choose between them: rotating the alignment rotates
    the columns, so each rotation has exactly the same set of constant columns,
    just in different places. Something stronger has to pick - see
    find_crc(), which tries all of them and lets the checksum decide.
    """
    out = {}
    for off in range(period):
        frames = [data[i:i + period]
                  for i in range(off, len(data) - period + 1, period)]
        if len(frames) >= 4:
            out[off] = frames
    return out


def rank_rotations(rots):
    """
    Order alignments by how much the first two columns look like a frame marker.

    The fallback for when no checksum closes. A framed protocol almost always
    opens with a constant header, often followed by a constant length byte, and
    a constant 0x00 is a weaker signal than a constant non-zero value - zero
    columns are usually padding or the high byte of a small measurand. Returns
    [(score, offset), ...], best first.
    """
    scored = []
    for off, frames in rots.items():
        n = len(frames)
        v0, n0 = Counter(f[0] for f in frames).most_common(1)[0]
        v1, n1 = Counter(f[1] for f in frames).most_common(1)[0]
        score = (n0 / n) + 0.5 * (n1 / n)
        if v0 != 0:
            score += 0.25
        if v1 != 0:
            score += 0.1
        scored.append((score, off))
    scored.sort(reverse=True)
    return scored


def column_table(frames):
    """Per-offset statistics across aligned frames."""
    if not frames:
        return []
    period = len(frames[0])
    rows = []
    for c in range(period):
        col = [f[c] for f in frames]
        uniq = len(set(col))
        # Does it count up once per frame (mod 256)? That is the sequence
        # counter, and finding it confirms the alignment is real.
        deltas = Counter((b - a) % 256 for a, b in zip(col, col[1:]))
        top_delta, top_n = deltas.most_common(1)[0]
        counts_up = top_delta == 1 and top_n > 0.8 * max(1, len(col) - 1)
        rows.append({
            "offset": c,
            "min": min(col),
            "max": max(col),
            "uniq": uniq,
            "const": uniq == 1,
            "value": col[0] if uniq == 1 else None,
            "counter": counts_up,
        })
    return rows


def print_columns(rows, frames):
    header("Byte columns")
    print(f"{len(frames)} aligned frames of {len(frames[0])} bytes\n")
    print(" off  min  max  uniq  note")
    print(" ---  ---  ---  ----  ----")
    for r in rows:
        note = ""
        if r["const"]:
            note = f"CONSTANT 0x{r['value']:02X}"
        elif r["counter"]:
            note = "counts +1 per frame (sequence counter)"
        elif r["uniq"] > 40:
            note = "varies a lot (measurand, or a checksum byte)"
        print(f" {r['offset']:>3}  {r['min']:>3}  {r['max']:>3}  "
              f"{r['uniq']:>4}  {note}")

    lead = rows[0]
    if lead["const"]:
        print(f"\n-> Offset 0 is constant 0x{lead['value']:02X}: the frame header.")
        if len(rows) > 1 and rows[1]["const"]:
            print(f"-> Offset 1 is constant 0x{rows[1]['value']:02X}: "
                  f"the length byte, if the frame carries one.")
    else:
        print("\n-> Offset 0 is NOT constant, so this alignment is suspect. "
              "Treat the offsets below as unconfirmed.")
    print(f"-> Candidate spec says header 0x{proto.HEADER:02X}, "
          f"length byte 0x{proto.LEN_BYTE:02X}, {proto.FRAME_LEN} bytes.")


def find_crc(rots, sample=200):
    """
    Try every candidate checksum, over every alignment, span and endianness.

    The alignment is searched too, and that is the point: a checksum that
    closes on hundreds of frames identifies the frame boundary beyond doubt,
    which nothing else here can do (see rotations()). So this both finds the
    checksum and confirms the alignment.

    Candidates are screened against `sample` frames and the winner is then
    re-verified against every frame, so a lucky match on a short run cannot
    get through.

    Returns (offset, name, start, end, endian) or None.
    """
    header("Checksum search")
    hits = []
    for off, frames in sorted(rots.items()):
        period = len(frames[0])
        screen = frames[:sample]
        for name, (func, width) in proto.CRC_FUNCS.items():
            end = period - width
            for start in range(0, 4):
                if end <= start:
                    continue
                for endian in ("big", "little"):
                    def closes(fs):
                        return all(
                            func(f[start:end]) ==
                            int.from_bytes(f[end:end + width], endian,
                                           signed=False)
                            for f in fs
                        )
                    if closes(screen) and closes(frames):
                        hits.append((off, name, start, end, endian, width,
                                     len(frames)))

    if not hits:
        print("No candidate checksum closes on any alignment.")
        print("Either there is no checksum in the last 1-2 bytes, or it is a")
        print("variant not in esc_protocol.CRC_FUNCS. Leave CRC_NAME = None:")
        print("the header + length-byte check is still a working resync.")
        return None

    for off, name, start, end, endian, width, n in hits:
        print(f"MATCH  alignment offset {off}: {name:<10} over bytes "
              f"[{start}:{end}], {width}-byte value stored {endian}-endian, "
              f"on all {n} frames")
    off, name, start, end, endian, _w, _n = hits[0]
    print("\n-> Put this in esc_protocol.py:")
    print(f"       CRC_NAME   = {name!r}")
    print(f"       CRC_SPAN   = ({start}, {end})")
    print(f"       CRC_ENDIAN = {endian!r}")
    return off, name, start, end, endian


def print_hexdump(frames, n=6):
    header(f"First {min(n, len(frames))} frames, raw")
    for f in frames[:n]:
        print("  " + f.hex(" "))


def print_decode(frames, poles, n=6):
    """Apply the candidate spec, so the numbers can be eyeballed on the bench."""
    header("Candidate spec applied (sanity-check these against the bench)")
    if len(frames[0]) != proto.FRAME_LEN:
        print(f"SKIPPED: discovered frame length {len(frames[0])} does not "
              f"match the candidate's {proto.FRAME_LEN}. Fix FRAME_LEN and "
              f"the SPEC offsets first - the column table above is the input "
              f"to that, not this preview.")
        return
    for f in frames[:n]:
        d = proto.decode(f, poles=poles)
        print(f"  seq={d['counter']:>8}  thr={_fmt(d['throttle_pct'], 1)}%  "
              f"eRPM={d['erpm']:>7}  rpm={_fmt(d['rpm'], 0)}  "
              f"{_fmt(d['volts'], 2)}V  {_fmt(d['amps'], 2)}A  "
              f"phase={_fmt(d['phase_amps'], 2)}A  "
              f"mos={_fmt(d['mos_temp_c'], 1)}C")


def _fmt(v, nd):
    return "--" if v is None else f"{v:.{nd}f}"


def calibrate(frames, known_volts, known_amps, known_rpm):
    """
    Derive scale factors from a reading you trust.

    Takes the mean of each 2-byte big-endian pair across the capture and
    divides your known value by it. The right pair is the one whose ratio
    comes out as a round-ish number near the candidate scale - the report
    shows all of them so you can see which, rather than being told.
    """
    header("Calibration")
    period = len(frames[0])
    print("Mean of every 2-byte big-endian pair, and what scale factor each")
    print("would need to produce your measured value.\n")
    print(" off   mean raw   " + "   ".join(
        f"{label:>14}" for label, v in (
            ("V/count", known_volts), ("A/count", known_amps),
            ("rpm/count", known_rpm)) if v is not None))
    for off in range(period - 1):
        vals = [int.from_bytes(f[off:off + 2], "big") for f in frames]
        mean = sum(vals) / len(vals)
        if mean == 0:
            continue
        cells = []
        for v in (known_volts, known_amps, known_rpm):
            if v is not None:
                cells.append(f"{v / mean:>14.5f}")
        print(f" {off:>3}   {mean:>9.1f}   " + "   ".join(cells))
    print("\n-> A ratio that lands on something like 0.1, 0.01, 0.0625 or 1.0")
    print("   at the offset the column table flagged as varying is your scale")
    print("   factor. Put it in esc_protocol.SCALES.")
    if known_rpm is not None:
        print("   For RPM, remember the stream carries eRPM: the ratio you want")
        print("   is the pole-count division, set as --poles, not a SCALES entry.")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def analyse(data, args):
    header("Capture summary")
    print(f"{len(data)} bytes")
    if not data:
        print("Nothing captured - see the sweep hints above.")
        return
    if args.seconds:
        print(f"{len(data) / args.seconds:.0f} bytes/s over "
              f"{args.seconds:.1f}s")

    period_info = best_period(data)
    if not period_info:
        header("Structure")
        print("No repeating frame structure found. The bytes are arriving but")
        print("they do not look framed - most likely the baud is wrong. Run")
        print("with --sweep. First 64 bytes:")
        print("  " + data[:64].hex(" "))
        return

    period, score = period_info
    header("Frame length")
    print(f"Repeats every {period} bytes (confidence {score:.2f})")
    if args.seconds:
        print(f"-> about {len(data) / period / args.seconds:.1f} frames/s")
    if period != proto.FRAME_LEN:
        print(f"-> DIFFERS from the candidate FRAME_LEN ({proto.FRAME_LEN}). "
              f"The capture wins; update esc_protocol.py.")

    rots = rotations(data, period)
    if not rots:
        print("Too few whole frames to analyse. Capture for longer.")
        return

    # The checksum picks the alignment where it can; otherwise fall back to
    # the header-shaped guess, and say which happened - an alignment confirmed
    # by a checksum is a fact, one chosen by a heuristic is not.
    crc_hit = find_crc(rots)
    if crc_hit:
        offset = crc_hit[0]
        how = "confirmed by the checksum"
    else:
        offset = rank_rotations(rots)[0][1]
        how = "guessed from the most header-like column, UNCONFIRMED"
    frames = rots[offset]

    header("Alignment")
    print(f"Frames start at byte offset {offset} - {how}")

    rows = column_table(frames)
    print_columns(rows, frames)
    print_hexdump(frames)
    print_decode(frames, args.poles)

    if any(v is not None for v in
           (args.calibrate_volts, args.calibrate_amps, args.calibrate_rpm)) \
            and frames:
        calibrate(frames, args.calibrate_volts, args.calibrate_amps,
                  args.calibrate_rpm)

    header("Next step")
    print("Capture again at a DIFFERENT steady throttle and compare the")
    print("column tables: the offsets that move with throttle are RPM,")
    print("current and phase current. That, plus the checksum result, is")
    print("everything esc_protocol.SPEC needs.")


def main():
    p = argparse.ArgumentParser(
        description="Discover and confirm the Hobbywing ESC telemetry frame "
                    "format. Read-only; never transmits.")
    p.add_argument("-p", "--port", default=proto.DEFAULT_PORT,
                   help=f"serial device (default {proto.DEFAULT_PORT})")
    p.add_argument("-b", "--baud", type=int, default=proto.DEFAULT_BAUD,
                   help=f"baud rate (default {proto.DEFAULT_BAUD})")
    p.add_argument("-t", "--seconds", type=float, default=5.0,
                   help="capture length (default 5)")
    p.add_argument("--sweep", action="store_true",
                   help="try a list of baud rates first")
    p.add_argument("--save", metavar="FILE",
                   help="write the raw bytes here for offline re-analysis")
    p.add_argument("--analyze", metavar="FILE",
                   help="analyse a previously saved capture instead of the port")
    p.add_argument("--poles", type=int, default=proto.DEFAULT_POLES,
                   help=f"motor magnet poles, for eRPM -> RPM "
                        f"(default {proto.DEFAULT_POLES}; 0 = eRPM only)")
    p.add_argument("--calibrate-volts", type=float,
                   help="bus voltage measured during the capture")
    p.add_argument("--calibrate-amps", type=float,
                   help="bus current measured during the capture")
    p.add_argument("--calibrate-rpm", type=float,
                   help="mechanical RPM measured during the capture")
    args = p.parse_args()

    if args.analyze:
        with open(args.analyze, "rb") as fh:
            data = fh.read()
        print(f"Analysing {args.analyze} ({len(data)} bytes)")
        # Byte rate is meaningless for a file unless the capture length is
        # also given, so suppress the frames/s line rather than invent it.
        args.seconds = None
        analyse(data, args)
        return

    if args.sweep:
        found = sweep(args.port, min(args.seconds, 3.0))
        if found:
            args.baud = found

    print(f"\nCapturing {args.seconds:.1f}s on {args.port} at {args.baud} baud...")
    data = capture(args.port, args.baud, args.seconds)

    if args.save:
        with open(args.save, "wb") as fh:
            fh.write(data)
        print(f"Raw bytes saved to {args.save}")

    analyse(data, args)


if __name__ == "__main__":
    main()
