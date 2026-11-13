#return to any default values of what codes have changed... might be handled through the script later on


import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import Mav_util


def run_reset():
    #####*****CHANGES*****#####
    # Verified writes and a closed connection, same as the other two subcodes.
    # This one runs right after the PWM test's reboot, so it is the most likely
    # of the three to be talking to a flight controller that is still settling -
    # which makes it the most likely to have had a write silently dropped.
    #
    # Mav_util.connect() returns None on a dead link instead of blocking.
    master = Mav_util.connect(tag="RESET")
    if master is None:
        print("[RESET] params NOT restored")
        return False
    #####*****END CHANGES*****#####

    #####*****CHANGES*****#####
    # LEFT EXACTLY AS IT WAS, as asked - not touching the values here.
    #
    # Flagging it rather than changing it, so it is written down somewhere:
    # "BATT9_VOLT_PIN": 257 looks like it was meant to be "BATT9_OPTIONS": 257,
    # since it mirrors BATT8_OPTIONS above it and 257 is not a valid ADC pin. As
    # it stands every body test leaves BATT9_VOLT_PIN = 257. It also does not
    # restore BATT8_VOLT_PIN (left at 14), BATT8_VOLT_MULT, BATT9_VOLT_MULT or
    # BATT9_OPTIONS.
    #
    # It no longer affects the analog port result either way: that test now
    # confirms every one of its own writes before rebooting, so it does not
    # depend on what state this left behind. Worth deciding on separately.
    #
    # Also note this function does not reboot, so BATTx_MONITOR = 8 is stored
    # but not applied until something else reboots the FC.
    #####*****END CHANGES*****#####
    Param_set = {
        "BATT8_OPTIONS": 257,
        "BATT8_MONITOR": 8,
        "BATT9_MONITOR": 8,
        "BATT9_VOLT_PIN": 257,
    }

    #####*****CHANGES*****#####
    # Each write is read back and retried instead of fire-and-forget with a
    # sleep(0.1). A restore that silently did not happen is worse than one that
    # failed loudly - it leaves the next run starting from a state nobody knows.
    try:
        failed = Mav_util.set_params(master, Param_set, tag="RESET")
        if failed:
            print(f"[RESET] could not confirm {failed} - params only partly restored")
            return False
        return True
    finally:
        Mav_util.close(master)
    #####*****END CHANGES*****#####
