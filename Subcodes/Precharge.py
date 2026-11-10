import lgpio

FET_CTL = 0
PRECHARGE = 12
CHIP = 4

h = None

#####*****CHANGES*****#####
# ---------------------------------------------------------------------------
# PRECHARGE IS DISABLED - hardware fault, PCB is being redesigned
# ---------------------------------------------------------------------------
# The precharge circuit on this board does not work, so every line that would
# energise the precharge path is commented out rather than deleted: the redesign
# will want them back. PRECHARGE (GPIO12, active LOW) is still claimed and still
# held at 1 (inactive), because an output parked in the OFF state is safer than
# a floating pin that could pull the line low on its own.
#
# What replaces it: read the input voltage, confirm it looks like the 25 V pack,
# and only then close the main FET. That is not a substitute for precharge - it
# does nothing about inrush into the ESC bus capacitance - but it does stop us
# closing the FET onto a missing, flat or wrong supply, which is the failure
# mode we can still detect from here.
#
# When the new board arrives: uncomment the marked lines in START_PRECHARGE and
# restore the wait-for-bus-voltage loop in the callers (see git history for
# commit c438af0, which had the correct ordering).

VIN_NOMINAL = 25.0      # the pack this rig runs on
VIN_MIN = 21.0          # below this: flat pack, or not the 25 V pack at all
VIN_MAX = 30.0          # above this: wrong supply - do not close the FET onto it
VIN_DEAD = 1.0          # below this there is effectively nothing there


def classify_input_voltage(volts):
    """
    Decide whether a measured input voltage is safe to switch on to.

    Pure function - takes the reading, does no I2C of its own. Each caller
    reads the INA228 with whatever locking it already uses and passes the
    number in, so there is one definition of "sane" and no bus contention.

    Returns (ok, message). The message is written to be shown to the operator
    as-is, so it says what was measured and what was expected.
    """
    if volts is None:
        return False, "no reading from the battery monitor - check the I2C wiring"

    if volts < VIN_DEAD:
        # Also the symptom if the monitor turns out to sit on the load side of
        # the FET, in which case it cannot see the pack until the FET closes.
        return False, (f"{volts:.2f} V - no input detected. Check the battery is "
                       f"connected and the monitor is upstream of the FET")

    if volts < VIN_MIN:
        return False, (f"{volts:.2f} V - input too low, expected about "
                       f"{VIN_NOMINAL:.0f} V (minimum {VIN_MIN:.0f} V). "
                       f"Pack flat or wrong pack")

    if volts > VIN_MAX:
        return False, (f"{volts:.2f} V - input too high, expected about "
                       f"{VIN_NOMINAL:.0f} V (maximum {VIN_MAX:.0f} V). "
                       f"Wrong supply connected")

    return True, f"{volts:.2f} V OK"
#####*****END CHANGES*****#####


def INITIALIZE_SYSTEM():
    global h

    try:
        if h is None:
            h = lgpio.gpiochip_open(CHIP)

        try:
            #####*****CHANGES*****#####
            # level=1 (precharge OFF) added. Without it the claim defaults to
            # level 0, which on this active-LOW line energises the precharge
            # path for the few lines until the gpio_write below turns it off.
            # Harmless when precharge worked; not something we want to pulse at
            # all now that the circuit is faulty.
            lgpio.gpio_claim_output(h, PRECHARGE, level=1)
            #####*****END CHANGES*****#####
        except:
            pass

        try:
            lgpio.gpio_claim_output(h, FET_CTL)
        except:
            pass

        lgpio.gpio_write(h, FET_CTL, 0)
        lgpio.gpio_write(h, PRECHARGE, 1)

        print("System initialized and precharge off, FET off")

    except Exception as e:
        print(f"PRECHARGE INIT ERROR: {e}")
        raise


def START_PRECHARGE():
    """
    DISABLED - the precharge circuit on this board is faulty.

    Kept as a no-op rather than removed so the call sites stay intact and the
    PCB redesign only has to uncomment one line. It deliberately leaves
    PRECHARGE at 1 (inactive) instead of energising it.
    """
    global h

    try:
        if h is None:
            raise RuntimeError("GPIO chip not initialized")

        #####*****CHANGES*****#####
        # Precharge disabled - hardware fault. Uncomment both lines below once
        # the redesigned board is in, and restore the wait-for-bus-voltage loop
        # in the callers.
        #
        # lgpio.gpio_write(h, PRECHARGE, 0)
        # print("Precharge on")

        lgpio.gpio_write(h, PRECHARGE, 1)   # held inactive
        print("Precharge DISABLED (hardware fault) - skipping")
        #####*****END CHANGES*****#####

    except Exception as e:
        print(f"PRECHARGE START ERROR: {e}")
        raise


def OPEN_FET():
    global h

    try:
        if h is None:
            raise RuntimeError("GPIO chip not initialized")

        lgpio.gpio_write(h, FET_CTL, 1)
        print("FET ON")

    except Exception as e:
        print(f"FET OPEN ERROR: {e}")
        raise


def TURN_OFF_PRECHARGE():
    #####*****CHANGES*****#####
    # Still called, still correct: it drives PRECHARGE to its inactive level,
    # which is now where the line lives permanently. Redundant while precharge
    # is disabled, but harmless, and it keeps the sequence intact for the
    # redesign. Nothing to comment out here.
    #####*****END CHANGES*****#####
    global h

    try:
        if h is None:
            raise RuntimeError("GPIO chip not initialized")

        lgpio.gpio_write(h, PRECHARGE, 1)
        print("Precharge off")

    except Exception as e:
        print(f"PRECHARGE OFF ERROR: {e}")
        raise


def CLOSE_FET():
    global h

    if h is None:
        return

    try:
        lgpio.gpio_write(h, FET_CTL, 0)
        print("FET OFF")

    except Exception as e:
        print(f"FET CLOSE ERROR: {e}")

def CLOSE_SYSTEM():
    global h

    if h is None:
        return

    try:
        lgpio.gpio_write(h, PRECHARGE, 1)
        lgpio.gpio_write(h, FET_CTL, 0)

        lgpio.gpiochip_close(h)

        print("GPIO CLOSED and Precharge off, FET off")

    except Exception as e:
        print(f"GPIO CLOSE ERROR: {e}")

    finally:
        h = None