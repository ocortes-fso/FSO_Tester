"""
#####*****CHANGES*****##### NEW FILE
Shared MAVLink helpers for the body test: write params and KNOW they landed.

WHY THIS EXISTS
---------------
The analog port test read wrong values on the first run and correct ones on the
second. The procedure was right - write params, reboot, read - but nothing in it
was confirmed: 8 fire-and-forget param_set_send calls, a reboot with no
COMMAND_ACK, a SET_MESSAGE_INTERVAL with no COMMAND_ACK. param_set writes are
PERSISTENT, so the first run had to land a whole configuration from scratch
while the second inherited whatever the first stored - which is exactly why
running it twice was a cure.

THE RULES THIS FILE FOLLOWS, learned the hard way
-------------------------------------------------
The first version of this file made the body test fail three DIFFERENT ways on
three consecutive runs of untouched hardware. Every one of those was caused by
being STRICTER than the code it replaced, not by the verification itself:

  1. It dropped the `time.sleep(1)` the original did between opening the port
     and waiting for a heartbeat, so wait_heartbeat() ran before the tty had
     settled -> spurious "no heartbeat". PORT_SETTLE_S puts that back. Do not
     remove it again.

  2. It treated a missing COMMAND_ACK for SET_MESSAGE_INTERVAL as a hard
     failure, so one dropped ack failed the whole ADC test with "CHECK CFG".
     Acks are now ADVISORY: the command is sent, the ack is waited for and
     reported, and the caller carries on either way. The old code got correct
     readings with no ack at all, so an absent ack can never be worse than the
     status quo.

  3. It shortened the post-reboot wait for the PWM test from the original's 15 s
     to 3 s, on no evidence. ArduPilot's servo outputs were not live yet, so the
     first four passes read low and only the last one - by which time the FC had
     finished booting - read high. reboot() now never waits LESS than the code
     it replaced: min_total_s reproduces the original sleep exactly, and the
     heartbeat check is added on top of it rather than instead of it.

  4. Retrying every parameter up to 6 times, each retry being a set AND a
     read-back, put ~96 messages plus ArduPilot's replies onto a 57600 link that
     already carries telemetry. More traffic means more drops means more
     retries - the retry loop fed itself. set_params() now works in ROUNDS: send
     the batch once, harvest the PARAM_VALUE replies ArduPilot sends for each
     set anyway, and only chase the ones that did not confirm. Typical traffic
     is one message per parameter.

The rule behind all four: verification may only ADD certainty, never remove
tolerance. When in doubt, do what the original did and wait longer.
"""

import time

from pymavlink import mavutil

SERIAL_PORT = "/dev/ttyAMA10"       # the debug port
BAUD_RATE = 57600

# --- opening the port -----------------------------------------------------
# The original slept 1 s between opening the port and waiting for a heartbeat,
# in both Body_Serial_test and Analog_port_test. Removing it caused spurious
# heartbeat failures. One place does it now. See rule 1 above.
PORT_SETTLE_S = 1.0
HEARTBEAT_TIMEOUT_S = 5.0

# --- parameters -----------------------------------------------------------
PARAM_SEND_GAP_S = 0.2          # between sends, as the original had
PARAM_HARVEST_S = 3.0           # listening for a whole batch's replies
PARAM_READ_TIMEOUT_S = 2.0      # one explicit read-back of one parameter
PARAM_ROUNDS = 3                # batches before giving up
PARAM_EPS = 0.01                # REAL32 round-trip tolerance

ACK_TIMEOUT_S = 2.0

# --- rebooting ------------------------------------------------------------
REBOOT_DOWN_S = 2.0             # let it actually go down before looking
REBOOT_RETRY_S = 1.5            # between reconnect attempts - NOT a tight loop
REBOOT_WAIT_S = 40.0            # ceiling on waiting for it to come back


def connect(timeout=HEARTBEAT_TIMEOUT_S, tag="MAV", settle_s=PORT_SETTLE_S):
    """
    Open the port, let it settle, wait for a heartbeat. Returns it, or None.

    The settle sleep is not optional - see rule 1 at the top of this file.

    None rather than an exception because every caller in the body test turns a
    dead link into a FAIL, not a crash.
    """
    master = mavutil.mavlink_connection(SERIAL_PORT, BAUD_RATE)
    time.sleep(settle_s)
    if not master.wait_heartbeat(timeout=timeout):
        print(f"[{tag}] no heartbeat in {timeout:.0f} s")
        close(master)
        return None
    return master


def close(master):
    """
    Close the connection.

    The subcodes never used to do this explicitly. CPython's reference counting
    closed them on return anyway, so this changes no behaviour - it just stops
    the lifetime depending on nobody else holding a reference.
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
        msg = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
        if msg is not None and _param_name(msg) == name:
            return msg.param_value
    return None


def _harvest_param_values(master, wanted, timeout=PARAM_HARVEST_S):
    """
    Listen for PARAM_VALUE and return the names from `wanted` that came back
    carrying the value we asked for.

    This is the cheap half of the verification, and the reason set_params does
    not need a retry storm. ArduPilot already answers every param_set with a
    PARAM_VALUE, so a batch of sets produces a batch of confirmations for free -
    no extra requests and no extra traffic. Only parameters that do NOT turn up
    here need chasing.
    """
    confirmed = set()
    deadline = time.time() + timeout
    while time.time() < deadline and len(confirmed) < len(wanted):
        msg = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
        if msg is None:
            continue
        name = _param_name(msg)
        if name in wanted and abs(msg.param_value - float(wanted[name])) <= PARAM_EPS:
            confirmed.add(name)
    return confirmed


def set_params(master, params, tag="MAV", rounds=PARAM_ROUNDS):
    """
    Write a dict of parameters and confirm every one of them.

    Returns the list of names that could not be confirmed - empty means the
    whole configuration is known to be stored. A non-empty list means the caller
    must NOT reboot: rebooting into a half-applied config and then reporting
    whatever it reads is the original bug.

    Rounds, not per-parameter retries - see rule 4 at the top of this file. On a
    healthy link this is one message per parameter and one round.
    """
    pending = {name: float(value) for name, value in params.items()}

    for round_no in range(1, rounds + 1):
        if not pending:
            break

        for name, value in pending.items():
            master.mav.param_set_send(
                master.target_system, master.target_component,
                name.encode("utf-8"), value,
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )
            time.sleep(PARAM_SEND_GAP_S)

        # Free confirmations first.
        for name in _harvest_param_values(master, pending):
            pending.pop(name, None)

        # Then chase only what is left.
        for name in list(pending):
            got = read_param(master, name)
            if got is not None and abs(got - pending[name]) <= PARAM_EPS:
                pending.pop(name)
            else:
                print(f"[{tag}] {name}: wanted {pending[name]}, read back {got} "
                      f"(round {round_no}/{rounds})")

        if pending and round_no < rounds:
            print(f"[{tag}] re-sending {sorted(pending)}")

    if pending:
        print(f"[{tag}] FAILED to confirm {sorted(pending)} after {rounds} rounds")
    return sorted(pending)


def send_command(master, command, *params, timeout=ACK_TIMEOUT_S, tag="MAV"):
    """
    Send a COMMAND_LONG and report whether it was acknowledged.

    ADVISORY, not fatal - rule 2 at the top of this file. The return value says
    whether an ACCEPTED ack arrived; False does NOT mean the command had no
    effect. Callers log it and carry on, because the code this replaced got
    correct results with no ack at all, so treating a missing ack as a failure
    can only ever be worse than the status quo.
    """
    args = list(params) + [0] * (7 - len(params))
    master.mav.command_long_send(
        master.target_system, master.target_component,
        command, 0, *args[:7],
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        ack = master.recv_match(type="COMMAND_ACK", blocking=True, timeout=0.5)
        if ack is not None and ack.command == command:
            if ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                return True
            print(f"[{tag}] command {command} rejected, result={ack.result}")
            return False
    print(f"[{tag}] no ACK for command {command} - carrying on anyway")
    return False


def reboot(master, tag="MAV", min_total_s=20.0, min_after_boot_s=5.0):
    """
    Reboot the FC and come back on a NEW connection. Returns it, or None.

    TWO waits, and both matter:

      min_total_s       measured from sending the reboot command. This
                        reproduces the fixed sleep the original code used - 20 s
                        for the analog port test, 15 s for the PWM test - so
                        this can never wait LESS than the code it replaced.
                        Shortening it to 3 s once left ArduPilot's servo outputs
                        not yet live, and only the final PWM channel read high.
      min_after_boot_s  measured from the heartbeat coming back, so a controller
                        that was slow to boot still gets its settling time.

    The old connection is CLOSED on purpose. A fresh file descriptor is the only
    way to be sure nothing read afterwards was queued before the reboot - the
    old `while recv_match(blocking=False): pass` flush stops at the first
    incomplete frame, and after a 20 s wait at 57600 baud that buffer has long
    overflowed. A pre-reboot frame carries the OLD configuration's reading.

    The ACK is best-effort: ArduPilot often reboots before the ack gets out, so
    its absence is not a failure. What IS checked is that the link came back,
    which a fixed sleep could never tell you.
    """
    print(f"[{tag}] rebooting the flight controller")
    t_command = time.time()

    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
        0,
        1,                      # param1 = 1 -> reboot autopilot
        0, 0, 0, 0, 0, 0,
    )
    if master.recv_match(type="COMMAND_ACK", blocking=True, timeout=1.0) is None:
        print(f"[{tag}] no reboot ACK (normal - the FC often goes down first)")

    close(master)

    # Let it get all the way down, so we cannot reconnect to the instance we
    # just asked to die and believe it rebooted.
    time.sleep(REBOOT_DOWN_S)

    fresh = None
    deadline = t_command + REBOOT_WAIT_S
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        candidate = mavutil.mavlink_connection(SERIAL_PORT, BAUD_RATE)
        time.sleep(PORT_SETTLE_S)
        if candidate.wait_heartbeat(timeout=2):
            fresh = candidate
            break
        close(candidate)
        # Deliberately not a tight open/close loop on the tty.
        time.sleep(REBOOT_RETRY_S)

    if fresh is None:
        print(f"[{tag}] did not come back within {REBOOT_WAIT_S:.0f} s of the reboot")
        return None

    t_boot = time.time()
    print(f"[{tag}] back up after {attempt} attempt(s) "
          f"({t_boot - t_command:.0f} s after the command)")

    # Wait out whichever of the two settling rules still has time left.
    while True:
        left = max(min_total_s - (time.time() - t_command),
                   min_after_boot_s - (time.time() - t_boot))
        if left <= 0:
            break
        time.sleep(min(left, 0.5))

    print(f"[{tag}] settled, {time.time() - t_command:.0f} s after the reboot command")
    return fresh
