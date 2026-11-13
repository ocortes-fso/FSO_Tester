import lgpio
import time
from pymavlink import mavutil

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import Mav_util

#####*****CHANGES*****#####
# Same treatment as Analog_port_test, and for the same reason: SERVOx_FUNCTION
# writes were fire-and-forget and the reboot was followed by a blind
# sleep(15). A dropped write left that channel on its old function, so the PWM
# readback measured a channel the FC was never asked to drive - a FAIL with no
# hint that the cause was a lost message rather than bad hardware.
#
# Now every write is read back and retried, the reboot is confirmed by the link
# coming back rather than by a fixed sleep, and the reading happens on a FRESH
# connection so nothing queued before the reboot can be mistaken for a result.
# See Subcodes/Mav_util.py.
#####*****END CHANGES*****#####


def run_pwm_test():
    Param_set = {
        "SERVO9_FUNCTION": 0,
        "SERVO10_FUNCTION": 0,
        "SERVO11_FUNCTION": 0,
        "SERVO12_FUNCTION": 0,
        "SERVO13_FUNCTION": 0,
    }

    #####*****CHANGES*****#####
    # ([], False) reads as a FAIL with no results in the GUI.
    master = Mav_util.connect(tag="PWM TEST")
    if master is None:
        return [], False

    failed = Mav_util.set_params(master, Param_set, tag="PWM TEST")
    if failed:
        print(f"[PWM TEST] could not confirm {failed} - not rebooting, "
              f"the readback would be meaningless")
        Mav_util.close(master)
        return [], False

    # SERVOx_FUNCTION needs a reboot to take effect.
    #
    # min_total_s=15 reproduces the original `time.sleep(15)` exactly. An
    # earlier version of this used 3 s and it broke the test: ArduPilot's servo
    # outputs were not live yet, so the first four passes of the readback below
    # measured low and only the last one - by which time the FC had finished
    # booting - read 1900. If this number is ever changed again it must only go
    # UP.
    master = Mav_util.reboot(master, tag="PWM TEST",
                             min_total_s=15.0, min_after_boot_s=5.0)
    if master is None:
        return [], False
    #####*****END CHANGES*****#####

    PWM_1, PWM_2, PWM_3, PWM_4, PWM_5 = 17, 18, 27, 23, 22
    PWMs = [PWM_1, PWM_2, PWM_3, PWM_4, PWM_5]

    High = 1900
    Low = 1100
    Channels = [9, 10, 11, 12, 13]

    h = lgpio.gpiochip_open(4)
    for pin in PWMs:
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_NONE)

    final_values = []

    for current_PWM in range(len(Channels)):
        for i in range(len(Channels)):
            val = High if i == current_PWM else Low
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
                0, Channels[i], val, 0, 0, 0, 0, 0
            )
            time.sleep(0.01)

        time.sleep(0.15)

        row = []
        for pin in PWMs:
            level = 0
            for _ in range(250):
                if lgpio.gpio_read(h, pin):
                    level = 1
                    break
                time.sleep(0.0002)
            row.append(High if level else Low)
        final_values.append(row[current_PWM])

    test_passed = (final_values == [High]*5) #returns true if passed, otherwise will be false 
    lgpio.gpiochip_close(h)

    Mav_util.close(master)      #####*****CHANGES*****##### was never closed

    return final_values, test_passed
