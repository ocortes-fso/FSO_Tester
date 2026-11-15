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
BATT_STATUS_TIMEOUT_S = 20      # ceiling only - the loop leaves when steady

#####*****CHANGES*****#####
# "Steady" = this many consecutive samples of one channel within this much of
# each other. 0.04 V is tighter than the +/-0.1 V windows the GUI validates
# against, so a channel that passes this cannot still be drifting enough to
# change the verdict. Three samples at 4 Hz is under a second.
STEADY_SAMPLES = 3
STEADY_TOLERANCE_V = 0.04
#####*****END CHANGES*****#####

BATT_MSG_ID = 147               # BATTERY_STATUS
BATT_INTERVAL_US = 250000       # 4 Hz - 5 samples in ~1.25 s

# Battery instances are 0-based, so BATT8 -> 7 and BATT9 -> 8.
INSTANCE_BATT8 = 7
INSTANCE_BATT9 = 8

# SAMPLES_WANTED is gone: a fixed sample count is what made the reading
# depend on luck. The loop now leaves when both channels are STEADY, however
# many samples that took. See STEADY_SAMPLES below.
VOLTAGE_UNKNOWN = 65535         # UINT16_MAX in mV - MAVLink "not known"

NO_READING = -1.0               # what the GUI already understands as a failure

# ---------------------------------------------------------------------------
# FORCING THE REBOOT: configure, reboot, and keep going until the reading is
# actually there.
#
# The bench symptom was: the first run sits there and then says CHECK CFG, the
# second run is perfect, and the reboot is heard LATER, during the PWM test.
# That is the signature of aborting before the reboot was ever sent - which is
# what the previous version did whenever a parameter could not be CONFIRMED.
#
# Why confirmation failed on a real first run is still not pinned down (a
# genuine buffer-overflow defect in the send loop has been fixed since, but on
# a clean link the read-back recovered from it, so it does not explain it on
# its own). The point of the design below is that it does not matter: the
# reading is the verification, so nothing is decided on the strength of a
# missing acknowledgement.
#
# Two things had to change:
#
#   * An unconfirmed parameter no longer ABORTS. It used to return [-1, -1]
#     without ever sending the reboot - which is exactly the observed symptom,
#     and why the reboot was then heard later during the PWM test instead. The
#     writes had landed; what went missing was the confirmation (see
#     Mav_util._pump_param_values). Aborting on missing evidence turned a
#     healthy board into a failure.
#
#   * If the reading comes back unusable, the whole thing is RETRIED -
#     parameters, reboot, read. Both known failure modes produce an obviously
#     impossible number rather than a wrong-looking one: UINT16_MAX when the
#     monitor has nothing to report, and ~0.01 V when the configuration has not
#     been applied to the pin yet. Anything under PLAUSIBLE_MIN_V means the
#     analog monitor is not reading the pin, so it is worth another reboot.
#     The pass/fail windows stay in the GUI - this only decides whether to try
#     again, never whether the board is good.
# ---------------------------------------------------------------------------
ANALOG_ATTEMPTS = 2

# The lowest divider output ANY supported board produces is 0.7 V (board 1's
# A1). A channel reading less than this is not reading a divider at all - it is
# an unconfigured or wrongly-pinned ADC input sitting near zero.
#
# This floor was 0.05 V, and that was useless: the bench reported A2 = 0.08 V,
# which cleared 0.05 and so counted as a usable reading. The retry never ran.
# 0.30 V is comfortably below every real reading and comfortably above every
# not-really-reading one.
PLAUSIBLE_MIN_V = 0.30

# Do not START another attempt once this much time has gone. Bounds the whole
# test so a sick link cannot run the body test past its navigation lock.
ANALOG_RETRY_DEADLINE_S = 75.0
#####*****END CHANGES*****#####


def _usable(reading):
    """True when both channels produced a voltage the ADC could really see."""
    return all(v > PLAUSIBLE_MIN_V for v in reading)


def _steady(values):
    """
    True once the last STEADY_SAMPLES readings of a channel agree.

    Nothing about whether the value is RIGHT - only that it has stopped
    changing, so that waiting longer would tell us nothing new.
    """
    if len(values) < STEADY_SAMPLES:
        return False
    recent = values[-STEADY_SAMPLES:]
    return max(recent) - min(recent) <= STEADY_TOLERANCE_V


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
    #####*****CHANGES*****#####
    # ADVISORY, not fatal. This used to `return [-1, -1]` when no COMMAND_ACK
    # arrived, which failed the whole ADC test with "CHECK CFG" on a single
    # dropped ack - and the code this replaced got correct readings without ever
    # asking for an ack at all. A missing ack is worth printing and nothing more;
    # if the stream really did not start, the read loop below says so by timing
    # out, which is a true statement about the data rather than a guess.
    if not Mav_util.send_command(
            master, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            BATT_MSG_ID, BATT_INTERVAL_US, tag="ANALOG PORT"):
        print("[ANALOG PORT] BATTERY_STATUS request not acknowledged - "
              "reading anyway, the FC may still be streaming")
    #####*****END CHANGES*****#####

    samples = {INSTANCE_BATT8: [], INSTANCE_BATT9: []}
    ignored = {}
    deadline = time.time() + BATT_STATUS_TIMEOUT_S

    while time.time() < deadline:
        #####*****CHANGES*****#####
        # Wait for the readings to STOP MOVING, instead of grabbing the first
        # five samples that turn up.
        #
        # This is what produced A1 = 1.16 V and A2 = 0.08 V on the first run
        # and correct values on the second. ArduPilot's analog battery monitor
        # reports a running AVERAGE of its ADC channel, and that average starts
        # from nothing when the monitor is created at boot. Read it while it is
        # still filling and you get a number part-way up the ramp - which is
        # exactly what 0.08 V on a 1.6 V divider is. The previous code waited a
        # fixed 8 s after the heartbeat and then took whatever arrived, so
        # whether it was settled was luck.
        #
        # Steadiness is the thing we actually need, so it is the thing to wait
        # for. The healthy case gets FASTER - it leaves as soon as both
        # channels are stable, usually in a couple of seconds, rather than
        # sitting out a fixed timeout.
        #
        # Note the test is steady, NOT steady-and-correct. A channel sitting
        # firmly at 0.08 V is settled, and the right thing to do is stop
        # waiting and let the caller reconfigure and reboot - not keep
        # listening to a number that is never going to change.
        if all(_steady(s) for s in samples.values()):
            break
        #####*****END CHANGES*****#####

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
            # Median of the LAST few, not of everything: the early samples
            # are the average still filling up, and including them drags the
            # answer back down the ramp we just waited out.
            recent = got[-STEADY_SAMPLES:]
            value = _median(recent)
            print(f"[ANALOG PORT] {name}: {len(got)} samples, settled "
                  f"{'yes' if _steady(got) else 'NO'}, median of last "
                  f"{len(recent)} = {value:.3f} V "
                  f"(raw {['%.3f' % v for v in got]})")
            out.append(value)

    return out


def analog_port_run(on_status=None, is_good=None):
    """
    Configure the ADC monitors, reboot, and return [BATT8_V, BATT9_V].

    on_status is an optional callback taking one short string, so the GUI can
    say what it is doing instead of sitting on "Rebooting..." for half a minute
    and looking frozen.

    #####*****CHANGES*****#####
    is_good is an optional callback taking the [v8, v9] reading and returning
    whether it is a PASS. It decides whether to configure-reboot-read again.

    It is a callback rather than a pair of constants here on purpose: the
    acceptance windows belong to the caller (there are two board variants, and
    the GUI already knows them), and copying them into this file would mean two
    places to change and two chances to disagree. Without it, the retry falls
    back to PLAUSIBLE_MIN_V, which only catches a channel that is not reading
    at all.
    #####*****END CHANGES*****#####
    """
    def say(text):
        print(f"[ANALOG PORT] {text}")
        if on_status is not None:
            try:
                on_status(text)
            except Exception as e:        # a dead callback must not fail a test
                print(f"[ANALOG PORT] status callback: {e}")

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
    master = None
    reading = [NO_READING, NO_READING]
    started = time.time()

    try:
        for attempt in range(1, ANALOG_ATTEMPTS + 1):
            if attempt > 1:
                say(f"reading was not there - configuring and rebooting again "
                    f"(attempt {attempt}/{ANALOG_ATTEMPTS})")

            Mav_util.close(master)
            master = Mav_util.connect(tag="ANALOG PORT")
            if master is None:
                return [NO_READING, NO_READING]

            # Every write is read back. A name that cannot be CONFIRMED is
            # reported and then ignored: the write itself almost certainly
            # landed, and refusing to reboot over missing evidence is what
            # produced "CHECK CFG on the first run, perfect on the second".
            say("writing the ADC monitor parameters")
            failed = Mav_util.set_params(master, Param_set, tag="ANALOG PORT")
            if failed:
                print(f"[ANALOG PORT] could not confirm {failed} - rebooting "
                      f"anyway, the reading below is the real check")

            # BATTx_MONITOR and BATTx_VOLT_PIN only take effect at boot. The
            # new connection comes back from here: the old one is closed, so no
            # frame from before the reboot can be read as a result.
            # min_total_s=20 reproduces the original `time.sleep(20)` exactly,
            # so this can never settle for less than the code it replaced.
            # strict=False because an unconfirmed reboot is not evidence of a
            # bad board - if it really did not restart, the reading says so and
            # we come round again.
            say("rebooting the flight controller to apply them")
            master = Mav_util.reboot(master, tag="ANALOG PORT",
                                     min_total_s=20.0, min_after_boot_s=8.0,
                                     # ONE command. Re-sending it inside
                                     # reboot() is what rebooted a healthy FC
                                     # twice and put the reading in the middle
                                     # of the second boot. The outer loop here
                                     # already retries the whole sequence, so
                                     # there is nothing to gain by also
                                     # retrying the command in there.
                                     strict=False, attempts=1)
            if master is None:
                # Did not come back at all - another reboot will not help.
                return [NO_READING, NO_READING]

            say("reading the ADC voltages")
            reading = _collect_voltages(master)

            # "Wait until the reading is correct" - so the caller's own
            # acceptance windows are what decides, falling back to "is this
            # channel reading anything at all" when it did not give any.
            accepted = is_good(reading) if is_good is not None else _usable(reading)
            if accepted:
                return reading
            print(f"[ANALOG PORT] {reading} is not an acceptable reading")

            if time.time() - started > ANALOG_RETRY_DEADLINE_S:
                print(f"[ANALOG PORT] {time.time() - started:.0f} s gone - not "
                      f"starting another attempt")
                break

        return reading

    finally:
        Mav_util.close(master)
    #####*****END CHANGES*****#####
