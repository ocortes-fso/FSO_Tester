#!/usr/bin/env python3
"""
esc_spindown.py - look at what the ESC reported after a SWEEP / RAMP cut.

Reads a log written by esc_gui.py (esc_YYYYmmdd_HHMMSS.csv), finds every
point where cmd_us drops to 0 (the signal cut), and for each one prints:

  * when the ESC's own throttle OUTPUT reached 0 after the cut - if this is
    late, the ESC kept driving the motor on its signal-loss failsafe;
  * when phase current reached ~0 - the same question, from the current side;
  * when eRPM first fell below a range of thresholds, and when it first read
    exactly 0 - a long low-eRPM tail means the stop threshold is too strict;
  * whether eRPM froze (same non-zero value repeated) - the ESC holding its
    last estimate rather than measuring;
  * the spindown_s the page recorded;
  * a decimated trace of the coast-down.

Read-only, stdlib only, runs on any machine:

    python3 esc_test/esc_spindown.py esc_test/logs/esc_20261123_101500.csv
    python3 esc_test/esc_spindown.py LOG.csv --every 1      # every frame
"""

from __future__ import annotations

import argparse
import csv
import sys

RPM_THRESHOLDS = (300, 200, 100, 50, 20, 10)
PHASE_ZERO_A = 0.2      # |phase current| at or below this counts as "not driving"
FREEZE_FRAMES = 10      # this many identical non-zero eRPM readings = frozen


def _num(row, key):
    v = row.get(key, "")
    if v in ("", None):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load(path):
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("t_s", "cmd_us", "spindown_s", "throttle_req_pct",
                  "throttle_pct", "erpm", "rpm", "amps", "phase_amps"):
            r[k] = _num(r, k)
    return rows


def find_cuts(rows):
    """Indices of the first cmd_us == 0 row after a non-zero cmd_us."""
    cuts, prev = [], None
    for i, r in enumerate(rows):
        c = r["cmd_us"]
        if c == 0 and prev not in (None, 0):
            cuts.append(i)
        if c is not None:
            prev = c
    return cuts


def first(rows, start, pred):
    for r in rows[start:]:
        if pred(r):
            return r
    return None


def report(rows, i_cut, every, tail_s):
    t0 = rows[i_cut]["t_s"]
    before = rows[i_cut - 1] if i_cut else None
    print("=" * 72)
    print(f"CUT at t_s={t0:.3f}  (last drive {before['cmd_us']:.0f} us, "
          f"{_f(before['rpm'], 0)} rpm, eRPM {_f(before['erpm'], 0)})"
          if before else f"CUT at t_s={t0:.3f}")

    def dt(r):
        return "never" if r is None else f"{r['t_s'] - t0:+.3f} s"

    end = first(rows, i_cut, lambda r: r["cmd_us"] not in (None, 0))
    i_end = rows.index(end) if end else len(rows)
    seg = rows[i_cut:i_end]

    print(f"  ESC throttle output -> 0 : "
          f"{dt(first(seg, 0, lambda r: r['throttle_pct'] == 0))}")
    print(f"  ESC throttle input  -> 0 : "
          f"{dt(first(seg, 0, lambda r: r['throttle_req_pct'] == 0))}")
    no_phase = first(seg, 0, lambda r: r["phase_amps"] is not None
                     and abs(r["phase_amps"]) <= PHASE_ZERO_A)
    print(f"  |phase A| <= {PHASE_ZERO_A}     : {dt(no_phase)}")
    for th in RPM_THRESHOLDS:
        print(f"  rpm  < {th:<4}            : "
              f"{dt(first(seg, 0, lambda r, th=th: r['rpm'] is not None and r['rpm'] < th))}")
    print(f"  eRPM == 0                : "
          f"{dt(first(seg, 0, lambda r: r['erpm'] == 0))}")
    rec = first(seg, 0, lambda r: r["spindown_s"] is not None)
    rec_txt = "none" if rec is None else f"{rec['spindown_s']:.3f} s"
    print(f"  page recorded spindown_s : {rec_txt}")

    # Frozen estimate: a run of identical non-zero eRPM readings.
    run_v, run_n, run_t = None, 0, None
    for r in seg:
        e = r["erpm"]
        if e and e == run_v:
            run_n += 1
            if run_n == FREEZE_FRAMES:
                print(f"  eRPM FROZEN at {e:.0f} from {run_t - t0:+.3f} s "
                      f"({FREEZE_FRAMES}+ identical frames)")
                break
        else:
            run_v, run_n, run_t = e, 1, r["t_s"]

    print(f"\n  {'t-cut':>8} {'cmd':>5} {'thr_in%':>7} {'thr_out%':>8} "
          f"{'phaseA':>7} {'busA':>6} {'eRPM':>7} {'rpm':>7}")
    t_stop = (rec["t_s"] if rec else seg[-1]["t_s"] if seg else t0) + tail_s
    start = max(0, i_cut - 5 * every)
    for k, r in enumerate(rows[start:i_end]):
        if r["t_s"] > t_stop:
            break
        if k % every:
            continue
        print(f"  {r['t_s'] - t0:+8.3f} {_f(r['cmd_us'], 0):>5} "
              f"{_f(r['throttle_req_pct'], 1):>7} {_f(r['throttle_pct'], 1):>8} "
              f"{_f(r['phase_amps'], 2):>7} {_f(r['amps'], 2):>6} "
              f"{_f(r['erpm'], 0):>7} {_f(r['rpm'], 0):>7}")


def _f(v, nd):
    return "--" if v is None else f"{v:.{nd}f}"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("csv")
    p.add_argument("--every", type=int, default=5,
                   help="print every Nth frame of the trace (default 5)")
    p.add_argument("--tail", type=float, default=1.0,
                   help="seconds of trace after the recorded stop (default 1)")
    args = p.parse_args()

    rows = load(args.csv)
    cuts = find_cuts(rows)
    if not cuts:
        sys.exit("no signal cut (cmd_us -> 0) found in this log")
    for i in cuts:
        report(rows, i, max(1, args.every), args.tail)


if __name__ == "__main__":
    main()
