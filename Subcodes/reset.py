#return to any default values of what codes have changed... might be handled through the script later on

import time
from pymavlink import mavutil

def run_reset():
    serial_port = "/dev/ttyAMA10"
    baud_rate = 57600
    master = mavutil.mavlink_connection(serial_port, baud_rate)
    master.wait_heartbeat()

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
        time.sleep(0.02)
