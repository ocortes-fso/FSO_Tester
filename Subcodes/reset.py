#return to any default values of what codes have changed... might be handled through the script later on

import time
from pymavlink import mavutil

def run_reset():
    serial_port = "/dev/ttyAMA10"
    baud_rate = 57600
    master = mavutil.mavlink_connection(serial_port, baud_rate)

    #####*****CHANGES*****#####
    # wait_heartbeat() used to be called with no timeout. This runs right after
    # the PWM test's reboot, so it is the most likely of the three to be called
    # while the FC is still coming back - and it would block forever.
    if not master.wait_heartbeat(timeout=5):
        print("[RESET] no heartbeat in 5 s - params NOT restored")
        return False
    #####*****END CHANGES*****#####

    Param_set = {
        "BATT8_OPTIONS": 257,
        "BATT8_MONITOR": 8,
        "BATT9_MONITOR": 8,
        "BATT9_VOLT_PIN": 257,
    }

    for name, value in Param_set.items():
        master.mav.param_set_send(
            master.target_system,
            master.target_component,
            name.encode('utf-8'),
            value,
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
        )
        time.sleep(0.1)

    return True    #####*****CHANGES*****##### so callers can tell it actually ran
