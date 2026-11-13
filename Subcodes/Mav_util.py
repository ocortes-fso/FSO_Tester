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
# ---------------------------------------------------------------------------
# ALL of these are read at CALL time, never used as default argument values.
# Python evaluates a default once, at def time, so `def f(t=TIMEOUT)` freezes a
# copy and makes the constant above unchangeable - which silently defeated a
# test that thought it had shortened a timeout. If you add a knob here, read it
# inside the function.
# ---------------------------------------------------------------------------
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

# Confirming the reboot really happened. ArduPilot heartbeats at 1 Hz on a
# telemetry serial, so REBOOT_SILENCE_S has to tolerate a couple of missed ones
# without calling it a reboot - 3 s is three heartbeat periods. The FC is down
# for several seconds anyway, so waiting that long to be sure costs nothing.
REBOOT_COMMAND_ATTEMPTS = 3
REBOOT_SILENCE_S = 3.0          # no heartbeat for this long = it really went down
REBOOT_DOWN_WAIT_S = 10.0       # how long to give it to go down at all


def connect(timeout=None, tag="MAV", settle_s=None):
    """
    Open the port, let it settle, wait for a heartbeat. Returns it, or None.

    The settle sleep is not optional - see rule 1 at the top of this file.

    None rather than an exception because every caller in the body test turns a
    dead link into a FAIL, not a crash.
    """
    # Read at call time, NOT as default arguments - see the note above the
    # constants. A default is evaluated once at import and then frozen.
    timeout = HEARTBEAT_TIMEOUT_S if timeout is None else timeout
    settle_s = PORT_SETTLE_S if settle_s is None else settle_s

    master = mavutil.mavlink_connection(SERIAL_PORT, BAUD_RATE)
    time.sleep(settle_s)
    if not master.wait_heartbeat(timeout=timeout):
        print(f"[{tag}] no heartbeat in {timeout:.0f} s")
        close(master)
        return None

    # The settle sleep above left the port unread, so the buffer is full before
    # we have asked for anything. Clear it, or the first reply we solicit is
    # the one the kernel discards. See drain().
    drain(master, tag=tag)
    return master


def drain(master, seconds=0.5, tag="MAV"):
    """
    Empty the port before soliciting a reply. Returns how many frames went.

    #####*****CHANGES*****#####
    Every sleep in this file leaves the serial port unread, and the kernel tty
    buffer fills whether or not anyone is listening - ~7 kB per second at 57600
    baud against a 4 kB buffer. So after a 1 s settle the buffer is already
    full, and the FIRST reply to arrive after it lands in a buffer that is
    overflowing: the kernel discards it.

    That is not theoretical. It cost the first PARAM_VALUE of every batch, and
    it cost the COMMAND_ACK for SET_MESSAGE_INTERVAL - the ack whose absence
    had to be made advisory, because it looked like the flight controller was
    not answering when in fact the answer was being thrown away locally.

    Called after a sleep and before anything is asked for, so nothing that
    matters can be in there to lose.
    #####*****END CHANGES*****#####
    """
    # On a real serial link this is the cheap, complete way to do it. The
    # simulator has no pyserial port underneath, hence the fallback loop.
    try:
        master.port.reset_input_buffer()
    except Exception:
        pass

    gone = 0
    deadline = time.time() + seconds
    while time.time() < deadline:
        if master.recv_match(blocking=True, timeout=0.05) is None:
            break
        gone += 1
    return gone


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


def read_param(master, name, timeout=None):
    """Ask for one parameter by name. Returns its value, or None."""
    timeout = PARAM_READ_TIMEOUT_S if timeout is None else timeout
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


def _pump_param_values(master, wanted, confirmed, seconds):
    """
    Spend `seconds` READING the link, adding any confirmed names to `confirmed`.

    #####*****CHANGES*****#####
    This replaces the blind `time.sleep(PARAM_SEND_GAP_S)` that used to pace the
    send loop.

    Eight parameters paced at 0.2 s meant 1.6 s during which NOTHING read the
    serial port. At 57600 baud that is ~9 kB of inbound telemetry against a
    4 kB kernel tty buffer, so the buffer overflows and the kernel throws data
    away - including all eight PARAM_VALUE replies the confirmation depends on.
    Measured against a simulated buffer: the old loop lost the whole batch,
    every time.

    HONESTLY, THOUGH: on a clean link that was survivable, because the explicit
    read-back then fetched every value again. So this is a real defect and a
    real waste of a 57600 link, but it is NOT proven to be what produced "CHECK
    CFG on the first run". What makes the test robust regardless is that the
    analog port test no longer treats an unconfirmed parameter as a reason to
    abort - see Analog_port_test.

    The pacing is unchanged - the same 0.2 s passes between sends - the port is
    just drained during it instead of ignored.
    #####*****END CHANGES*****#####
    """
    deadline = time.time() + seconds
    while True:
        left = deadline - time.time()
        if left <= 0:
            break
        msg = master.recv_match(type="PARAM_VALUE", blocking=True,
                                timeout=min(0.2, left))
        if msg is None:
            continue
        name = _param_name(msg)
        if (name in wanted and name not in confirmed
                and abs(msg.param_value - float(wanted[name])) <= PARAM_EPS):
            confirmed.add(name)
    return confirmed


def _harvest_param_values(master, wanted, timeout=None):
    """
    Listen for PARAM_VALUE and return the names from `wanted` that came back
    carrying the value we asked for.

    This is the cheap half of the verification, and the reason set_params does
    not need a retry storm. ArduPilot already answers every param_set with a
    PARAM_VALUE, so a batch of sets produces a batch of confirmations for free -
    no extra requests and no extra traffic. Only parameters that do NOT turn up
    here need chasing.
    """
    timeout = PARAM_HARVEST_S if timeout is None else timeout
    return _pump_param_values(master, wanted, set(), timeout)


def set_params(master, params, tag="MAV", rounds=None):
    """
    Write a dict of parameters and confirm every one of them.

    Returns the list of names that could not be confirmed - empty means the
    whole configuration is known to be stored. A non-empty list means the caller
    must NOT reboot: rebooting into a half-applied config and then reporting
    whatever it reads is the original bug.

    Rounds, not per-parameter retries - see rule 4 at the top of this file. On a
    healthy link this is one message per parameter and one round.
    """
    rounds = PARAM_ROUNDS if rounds is None else rounds
    pending = {name: float(value) for name, value in params.items()}

    for round_no in range(1, rounds + 1):
        if not pending:
            break

        confirmed = set()
        for name, value in list(pending.items()):
            master.mav.param_set_send(
                master.target_system, master.target_component,
                name.encode("utf-8"), value,
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )
            #####*****CHANGES*****#####
            # Pace exactly as before, but DRAIN the port during the gap instead
            # of sleeping on it. A blind sleep here overflowed the tty buffer
            # and destroyed the very replies this function waits for. See
            # _pump_param_values.
            _pump_param_values(master, pending, confirmed, PARAM_SEND_GAP_S)
            #####*****END CHANGES*****#####

        # Free confirmations - most of them arrived during the loop above.
        _pump_param_values(master, pending, confirmed, PARAM_HARVEST_S)
        for name in confirmed:
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


def send_command(master, command, *params, timeout=None, tag="MAV"):
    """
    Send a COMMAND_LONG and report whether it was acknowledged.

    ADVISORY, not fatal - rule 2 at the top of this file. The return value says
    whether an ACCEPTED ack arrived; False does NOT mean the command had no
    effect. Callers log it and carry on, because the code this replaced got
    correct results with no ack at all, so treating a missing ack as a failure
    can only ever be worse than the status quo.
    """
    timeout = ACK_TIMEOUT_S if timeout is None else timeout
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


def _wait_for_silence(master, silence_s=None, timeout=None, tag="MAV"):
    """
    Wait until the link goes quiet, i.e. the flight controller really went down.

    Returns True once no heartbeat has arrived for `silence_s`. Returns False if
    it kept heartbeating for the whole `timeout`, which means the reboot command
    had no effect - and that is the whole point of this function. A reboot and a
    lost reboot command look identical from the "wait for a heartbeat" side,
    because a heartbeat comes back either way. Silence is the only positive
    evidence that it actually restarted.
    """
    silence_s = REBOOT_SILENCE_S if silence_s is None else silence_s
    timeout = REBOOT_DOWN_WAIT_S if timeout is None else timeout

    deadline = time.time() + timeout
    last_seen = time.time()
    while time.time() < deadline:
        if master.recv_match(type="HEARTBEAT", blocking=True, timeout=0.3) is not None:
            last_seen = time.time()
        elif time.time() - last_seen >= silence_s:
            print(f"[{tag}] link went quiet - the FC is rebooting")
            return True
    return False


def reboot(master, tag="MAV", min_total_s=20.0, min_after_boot_s=5.0,
           strict=True, attempts=None):
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

    #####*****CHANGES*****#####
    # CONFIRM THE REBOOT BY WATCHING THE LINK GO SILENT, and re-send if it
    # does not. This is the hole that produced "the Durandal does not reboot,
    # the ADC test says CHECK CFG, and then I hear it reboot when the PWM test
    # starts writing parameters".
    #
    # The previous version sent the command once, closed the port, and then
    # waited for a heartbeat. But a heartbeat comes back in BOTH cases - whether
    # the FC rebooted or never went down at all - so a lost reboot command was
    # indistinguishable from a successful one. The code then waited out its 20 s,
    # read the battery monitors while the OLD configuration was still running,
    # got UINT16_MAX from them, and reported no-reading. The reboot heard later
    # was the PWM test's, which is a separate command that did get through.
    #
    # An FC that is rebooting stops talking, so silence is the one positive
    # signal that it really went down. The connection is deliberately kept open
    # until then - it has to be, to hear the silence - and only closed
    # afterwards, which still means the reading below happens on a fresh file
    # descriptor that cannot hold a pre-reboot frame.
    #
    # strict=True  -> never observing the silence is a failure, return None.
    # strict=False -> say so loudly but carry on and reconnect anyway, because
    #                 the caller re-reads and retries, and the READING is then
    #                 the real verification. Silence detection is evidence, not
    #                 an authority: a heartbeat that slips through the window
    #                 must not be able to fail a test the old code passed.
    attempts = REBOOT_COMMAND_ATTEMPTS if attempts is None else attempts
    went_down = False
    for attempt in range(1, attempts + 1):
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
        elif (ack.command == mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN
                and ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED):
            # Worth saying out loud: ArduPilot refuses to reboot when armed,
            # and that is a different problem from a lost message.
            print(f"[{tag}] the FC REFUSED the reboot, result={ack.result}")

        if _wait_for_silence(master, tag=tag):
            went_down = True
            break

        print(f"[{tag}] still talking {REBOOT_DOWN_WAIT_S:.0f} s after the reboot "
              f"command - it did not take (attempt {attempt}/{attempts})")

    if not went_down:
        print(f"[{tag}] never saw the link go quiet. The parameters are stored "
              f"but may not be applied")
        if strict:
            close(master)
            return None
        print(f"[{tag}] carrying on anyway - the reading decides")
    #####*****END CHANGES*****#####

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

    # Same as in connect(): the settling waits above left the port unread, and
    # this is exactly where the SET_MESSAGE_INTERVAL ack was being lost.
    drain(fresh, tag=tag)

    print(f"[{tag}] settled, {time.time() - t_command:.0f} s after the reboot command")
    return fresh
