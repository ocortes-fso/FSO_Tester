"""
#####*****CHANGES*****##### NEW FILE
Shared MAVLink helpers for the body test: write params and KNOW they landed.

WHY THIS EXISTS
---------------
The analog port test read wrong values on the first run and correct ones on the
second. The procedure was right - write params, reboot, read - but nothing in
it was ever confirmed. Each run sent, blind:

    8 x param_set_send   fire-and-forget, sleep(0.2), no PARAM_VALUE read-back
    1 x REBOOT_SHUTDOWN  no COMMAND_ACK
    1 x SET_MESSAGE_INTERVAL   no COMMAND_ACK

and BATTx_MONITOR / BATTx_VOLT_PIN only take effect at boot.

That is what made running it twice a cure. param_set writes are PERSISTENT, so
the first run has to land a whole configuration from scratch, while the second
run inherits whatever the first managed to store and only needs the reboot. Lose
one message on the first run - say BATT8_VOLT_PIN - and the FC reboots with the
monitor enabled but pointed at the wrong ADC pin, which reads as a plausible but
wrong number rather than as an error.

So every function in here verifies. A param write is read back and compared and
retried; a command waits for its ACK; a reboot is confirmed by the link going
away and coming back.

THE OTHER HALF: reading across a reboot
---------------------------------------
reboot() deliberately CLOSES the connection and opens a new one. Keeping the old
one would leave pre-reboot BATTERY_STATUS frames sitting in the receive buffer,
and the old flush (`while recv_match(blocking=False): pass`) could not be relied
on to clear them - it stops at the first incomplete frame, and after a 20 s wait
at 57600 baud that buffer has long since overflowed. A frame from before the
reboot carries the OLD configuration's reading. A new file descriptor cannot
contain one.

These helpers are shared by Analog_port_test, PWM_test and reset so there is one
definition of "the write landed" rather than three.
"""

import time

from pymavlink import mavutil

SERIAL_PORT = "/dev/ttyAMA10"       # the debug port
BAUD_RATE = 57600

# --- timeouts, all bounded so nothing here can hang the body test ---------
HEARTBEAT_TIMEOUT_S = 5.0
# These two set the worst case, and the worst case has to stay under the body
# test's navigation lock (MasterUI.BODY_LOCK_MAX_S) or the lock releases while
# the flight controller is still mid-reboot - which is the one thing it exists
# to prevent. At 4 attempts x 1.5 s the three subcodes together came to ~220 s
# against a 180 s lock. 3 x 1.0 s brings that to ~165 s, and the lock was raised
# to 300 s to keep real headroom.
#
# On a healthy link none of this is reached: a param confirms on the first try
# in a few hundred ms, and the whole analog test is faster than it used to be
# because the blind sleep(20) is gone.
# MANY SHORT ATTEMPTS, not a few long ones. Re-sending a parameter that already
# landed is harmless - the write is idempotent and the read-back confirms it
# either way - so a short timeout costs nothing but a redundant write, while a
# low attempt count costs correctness. With a 40% drop rate, 3 attempts leave a
# 6% chance per parameter of never landing, which across 8 parameters is a 40%
# chance of the run failing; 6 attempts bring that to 0.4% and 3%.
#
# The worst case still has to stay under MasterUI.BODY_LOCK_MAX_S (300 s), or
# the navigation lock releases while the FC is mid-reboot. 6 x 0.6 s across the
# three subcodes is about 77 s of parameter work, ~180 s all in.
PARAM_READ_TIMEOUT_S = 0.6      # waiting for one PARAM_VALUE
PARAM_SET_ATTEMPTS = 6          # write + read-back tries before giving up
PARAM_RETRY_SLEEP_S = 0.15      # breather between attempts, so a congested
                                # link gets a moment to drain
PARAM_EPS = 0.01                # REAL32 round-trip tolerance
ACK_TIMEOUT_S = 2.0

# After the reboot command: how long the FC is expected to be unreachable, how
# long to keep trying for it, and how long to let it settle once it answers.
REBOOT_DOWN_S = 2.0
REBOOT_WAIT_S = 30.0
REBOOT_SETTLE_S = 8.0


def connect(timeout=HEARTBEAT_TIMEOUT_S, tag="MAV"):
    """
    Open the port and wait for a heartbeat. Returns the connection, or None.

    None rather than an exception because every caller in the body test turns a
    dead link into a FAIL, not a crash.
    """
    master = mavutil.mavlink_connection(SERIAL_PORT, BAUD_RATE)
    if not master.wait_heartbeat(timeout=timeout):
        print(f"[{tag}] no heartbeat in {timeout:.0f} s")
        close(master)
        return None
    return master


def close(master):
    """
    Close the connection.

    None of the body test's subcodes used to do this, so a run left four
    mavlink_connection() objects open on the same /dev/ttyAMA10. pyserial takes
    no exclusive lock by default, so two live readers on one tty split the byte
    stream between them and both see corrupt MAVLink. CPython's reference
    counting usually cleaned them up on return, which is why it mostly worked -
    but that is luck, not design.
    """
    if master is None:
        return
    try:
        master.close()
    except Exception as e:
        print(f"[MAV] close: {e}")


def _param_name(msg):
    """PARAM_VALUE.param_id arrives as str or bytes, NUL-padded either way."""
    pid = getattr(msg, "param_id", "")
    if isinstance(pid, (bytes, bytearray)):
        pid = pid.decode("utf-8", "replace")
    return pid.replace("\x00", "").strip()


def read_param(master, name, timeout=PARAM_READ_TIMEOUT_S):
    """Ask for one parameter by name. Returns its value, or None."""
    master.mav.param_request_read_send(
        master.target_system, master.target_component,
        name.encode("utf-8"), -1,           # -1 = look it up by name
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.3)
        if msg is not None and _param_name(msg) == name:
            return msg.param_value
    return None


def set_param(master, name, value, attempts=PARAM_SET_ATTEMPTS, tag="MAV"):
    """
    Write one parameter and confirm it by reading it back. Returns True/False.

    This is the fix for the first-run bug. A dropped param_set used to be
    invisible: the FC never wrote it, never replied, and the code moved on and
    rebooted into a half-applied configuration.

    The read-back is an explicit param_request_read rather than trusting the
    PARAM_VALUE that ArduPilot sends in reply to a set, because that reply is
    exactly as droppable as the set was. Asking for the stored value is the only
    thing that actually proves the write happened.
    """
    for attempt in range(1, attempts + 1):
        master.mav.param_set_send(
            master.target_system, master.target_component,
            name.encode("utf-8"), float(value),
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
        )
        got = read_param(master, name)
        if got is not None and abs(got - float(value)) <= PARAM_EPS:
            if attempt > 1:
                print(f"[{tag}] {name} = {value} confirmed on attempt {attempt}")
            return True
        print(f"[{tag}] {name}: wrote {value}, read back {got} "
              f"(attempt {attempt}/{attempts})")
        time.sleep(PARAM_RETRY_SLEEP_S)

    print(f"[{tag}] FAILED to set {name} = {value} after {attempts} attempts")
    return False


def set_params(master, params, tag="MAV"):
    """
    Write a dict of parameters, each one verified.

    Returns the list of names that could not be confirmed - empty means the
    whole configuration is known to be stored. Callers should treat a non-empty
    list as a failure rather than rebooting into a partial config, which is
    precisely what used to happen.
    """
    failed = []
    for name, value in params.items():
        if not set_param(master, name, value, tag=tag):
            failed.append(name)
    return failed


def send_command(master, command, *params, attempts=3, timeout=ACK_TIMEOUT_S, tag="MAV"):
    """
    Send a COMMAND_LONG and wait for its COMMAND_ACK. Returns True/False.

    Used for SET_MESSAGE_INTERVAL, which was previously sent once into the void
    - if it was lost, no BATTERY_STATUS stream ever started and the read loop
    just timed out.
    """
    args = list(params) + [0] * (7 - len(params))
    for attempt in range(1, attempts + 1):
        master.mav.command_long_send(
            master.target_system, master.target_component,
            command, 0, *args[:7],
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            ack = master.recv_match(type="COMMAND_ACK", blocking=True, timeout=0.3)
            if ack is not None and ack.command == command:
                if ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                    return True
                print(f"[{tag}] command {command} rejected, result={ack.result}")
                return False
        print(f"[{tag}] no ACK for command {command} "
              f"(attempt {attempt}/{attempts})")
    return False


def reboot(master, tag="MAV", settle_s=REBOOT_SETTLE_S):
    """
    Reboot the FC and come back on a NEW connection. Returns it, or None.

    The old connection is closed on purpose - see the note at the top of this
    file. A fresh file descriptor is the only way to be certain that nothing
    read afterwards was queued before the reboot.

    The ACK is best-effort: ArduPilot frequently reboots before the ack gets
    out of the door, so its absence is not treated as a failure. What IS checked
    is that the link actually came back, which is the thing a fixed sleep(20)
    could never tell you.
    """
    print(f"[{tag}] rebooting the flight controller")
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
        0,
        1,                      # param1 = 1 -> reboot autopilot
        0, 0, 0, 0, 0, 0,
    )
    ack = master.recv_match(type="COMMAND_ACK", blocking=True, timeout=1.0)
    if ack is None:
        print(f"[{tag}] no reboot ACK (normal - the FC often goes down first)")

    close(master)

    # Let it get all the way down before trying again, so we cannot reconnect
    # to the instance we just asked to die and believe it rebooted.
    time.sleep(REBOOT_DOWN_S)

    deadline = time.time() + REBOOT_WAIT_S
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        fresh = mavutil.mavlink_connection(SERIAL_PORT, BAUD_RATE)
        if fresh.wait_heartbeat(timeout=2):
            print(f"[{tag}] back up after {attempt} attempt(s); "
                  f"settling for {settle_s:.0f} s")
            # The analog monitors read nonsense until their filters fill - this
            # is where the 0.01 V readings came from.
            time.sleep(settle_s)
            return fresh
        close(fresh)

    print(f"[{tag}] flight controller did not come back within {REBOOT_WAIT_S:.0f} s")
    return None
