import time

from pymavlink import mavutil

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import Mav_util

#need to add voltage divider inside the DSUB cap

#####*****CHANGES*****#####
# ---------------------------------------------------------------------------
# WHY THIS WAS REWRITTEN - the "first run reads rubbish" bug
# ---------------------------------------------------------------------------
# The procedure was always right: configure BATT8/BATT9 as analog voltage
# monitors on ADC pins 14/15, reboot so the configuration takes effect, then
# read the voltages back. What was wrong is that NONE of it was confirmed.
#
# The old code sent 8 param_set_send calls fire-and-forget with a sleep(0.2)
# between them, then a reboot command with no COMMAND_ACK, then a
# SET_MESSAGE_INTERVAL with no COMMAND_ACK, and then read the first
# BATTERY_STATUS that turned up. Any one of those messages going missing on a
# busy 57600 link produced a wrong reading with no indication that anything
# had failed.
#
# That is also why running it a second time fixed it. param_set writes are
# PERSISTENT in the flight controller, so the first run has to land a whole
# configuration from nothing, while a second run inherits whatever the first
# managed to store and only needs the reboot to succeed. The first run is
# therefore the fragile one, every time - which matches the symptom exactly.
#
# Four separate things could produce the values seen on the bench, and all four
# are now closed:
#
#   * A DROPPED PARAM WRITE -> the FC reboots with the monitor enabled but
#     pointed at the wrong ADC pin, which reads ~0.01 V. Every write is now
#     read back and retried (Mav_util.set_params), and a configuration that
#     cannot be confirmed aborts instead of rebooting into a partial state.
#
#   * A STALE PRE-REBOOT FRAME -> carries the OLD configuration's reading. The
#     old `while recv_match(blocking=False): pass` flush could not be relied on
#     to clear it: it stops at the first incomplete frame, and after a 20 s wait
#     at 57600 baud the serial buffer has long overflowed. Mav_util.reboot()
#     now CLOSES the connection and opens a new one, so nothing read afterwards
#     can possibly predate the reboot.
#
#   * voltages[0] == UINT16_MAX -> MAVLink's "this voltage is unknown", which is
#     65535 mV. Divided by 1000 that is the 65.5 V - "decenas de voltios" - seen
#     on the bench. It is a sentinel, not a measurement, and it is now rejected
#     rather than reported as a reading.
#
#   * THE WRONG BATTERY INSTANCE -> SET_MESSAGE_INTERVAL on message 147 sets the
#     rate for BATTERY_STATUS as a message, i.e. for every instance, so
#     instance 0 (the real pack) arrives whether we want it or not. The old code
#     reacted to any unexpected instance by setting BOTH voltages to -1 and
#     breaking out of the loop - so a single frame from the main battery failed
#     the test, and could even overwrite a good reading that had already
#     arrived. Other instances are now simply ignored.
#
# And one accuracy fix: the GUI validates against +/-0.1 V windows, but the old
# code kept the FIRST sample of each channel. ADC noise landed straight in that
# window. Several samples are now taken and the MEDIAN used, which also throws
# out a single rogue frame outright.
# ---------------------------------------------------------------------------

# How long to wait for BATTERY_STATUS on both channels after the reboot before
# giving up. The FC has already had its settle time by then, so if nothing is
# coming it is not going to.
BATT_STATUS_TIMEOUT_S = 10

BATT_MSG_ID = 147               # BATTERY_STATUS
BATT_INTERVAL_US = 250000       # 4 Hz - 5 samples in ~1.25 s

# Battery instances are 0-based, so BATT8 -> 7 and BATT9 -> 8.
INSTANCE_BATT8 = 7
INSTANCE_BATT9 = 8

SAMPLES_WANTED = 5              # per channel, median taken
VOLTAGE_UNKNOWN = 65535         # UINT16_MAX in mV - MAVLink "not known"

NO_READING = -1.0               # what the GUI already understands as a failure
#####*****END CHANGES*****#####


def _median(values):
    """Median of a non-empty list. One rogue sample cannot move it."""
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _collect_voltages(master):
    """
    Sample BATT8 and BATT9 and return their median pin voltages.

    Returns [v8, v9], with NO_READING for a channel that produced no usable
    sample. "Usable" excludes UINT16_MAX, which is MAVLink's way of saying the
    monitor has no value for this - not a 65 V measurement.
    """
    if not Mav_util.send_command(
            master, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            BATT_MSG_ID, BATT_INTERVAL_US, tag="ANALOG PORT"):
        print("[ANALOG PORT] the FC never acknowledged the BATTERY_STATUS "
              "request - no stream to read")
        return [NO_READING, NO_READING]

    samples = {INSTANCE_BATT8: [], INSTANCE_BATT9: []}
    ignored = {}
    deadline = time.time() + BATT_STATUS_TIMEOUT_S

    while time.time() < deadline:
        if all(len(s) >= SAMPLES_WANTED for s in samples.values()):
            break

        msg = master.recv_match(type='BATTERY_STATUS', blocking=True, timeout=1)
        if msg is None:
            continue

        if msg.id not in samples:
            # Another battery instance - instance 0 is the real pack and it
            # shows up on this stream too. Count it and move on; it says
            # nothing about the analog port either way.
            ignored[msg.id] = ignored.get(msg.id, 0) + 1
            continue

        millivolts = msg.voltages[0]
        if millivolts == VOLTAGE_UNKNOWN:
            # The monitor is not reporting a voltage. Reading this as 65.5 V is
            # what produced the "tens of volts" values on the bench.
            continue

        samples[msg.id].append(millivolts / 1000.0)

    if ignored:
        print(f"[ANALOG PORT] ignored BATTERY_STATUS from other instances: {ignored}")

    out = []
    for instance, name in ((INSTANCE_BATT8, "BATT8"), (INSTANCE_BATT9, "BATT9")):
        got = samples[instance]
        if not got:
            print(f"[ANALOG PORT] no usable {name} reading in "
                  f"{BATT_STATUS_TIMEOUT_S} s")
            out.append(NO_READING)
        else:
            value = _median(got)
            print(f"[ANALOG PORT] {name}: {len(got)} samples, median "
                  f"{value:.3f} V (raw {['%.3f' % v for v in got]})")
            out.append(value)

    return out


def analog_port_run():
    Param_set = {
        "BATT8_OPTIONS": 1,
        "BATT8_VOLT_MULT": 1,
        "BATT8_MONITOR": 3,
        "BATT8_VOLT_PIN": 14,
        "BATT9_OPTIONS": 1,
        "BATT9_VOLT_MULT": 1,
        "BATT9_MONITOR": 3,
        "BATT9_VOLT_PIN": 15,
    }

    #####*****CHANGES*****#####
    # Mav_util.connect() does the open + wait_heartbeat and returns None on a
    # dead link. [-1, -1] is the "could not configure" signal the GUI already
    # renders as "COULDNT WRITE PARAMS - CHECK CFG".
    master = Mav_util.connect(tag="ANALOG PORT")
    if master is None:
        return [NO_READING, NO_READING]

    try:
        # Every write is read back and retried. If the configuration cannot be
        # confirmed we stop HERE rather than rebooting into a half-applied
        # state and reporting whatever it happens to read - which is the bug.
        failed = Mav_util.set_params(master, Param_set, tag="ANALOG PORT")
        if failed:
            print(f"[ANALOG PORT] could not confirm {failed} - not rebooting, "
                  f"the reading would be meaningless")
            return [NO_READING, NO_READING]

        # BATTx_MONITOR and BATTx_VOLT_PIN only take effect at boot. The new
        # connection comes back from here: the old one is closed, so no frame
        # from before the reboot can be read as a result.
        master = Mav_util.reboot(master, tag="ANALOG PORT")
        if master is None:
            return [NO_READING, NO_READING]

        return _collect_voltages(master)

    finally:
        Mav_util.close(master)
    #####*****END CHANGES*****#####
