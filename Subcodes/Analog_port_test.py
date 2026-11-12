import time
from pymavlink import mavutil

#need to add voltage divider inside the DSUB cap

#####*****CHANGES*****#####
# How long to wait for BATTERY_STATUS on both channels after the reboot before
# giving up. The FC has already had its 20 s settle by then, so if nothing is
# coming it is not going to.
BATT_STATUS_TIMEOUT_S = 10
#####*****END CHANGES*****#####


def analog_port_run():
    serial_port = "/dev/ttyAMA10" #debug port
    baud_rate = 57600

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

    master = mavutil.mavlink_connection(serial_port, baud_rate)
    time.sleep(1)

    #####*****CHANGES*****#####
    # wait_heartbeat() used to be called with no timeout, so an unresponsive
    # flight controller blocked here forever and hung the whole body test.
    # [-1, -1] is the "could not write params" signal the GUI already knows.
    if not master.wait_heartbeat(timeout=5):
        print("[ANALOG PORT] no heartbeat in 5 s - cannot write params")
        return [-1, -1]
    #####*****END CHANGES*****#####

    for name, value in Param_set.items():
        master.mav.param_set_send(
            master.target_system,
            master.target_component,
            name.encode('utf-8'),
            value,
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
        )
        time.sleep(0.2)

    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
        0,
        1,
        0, 0, 0, 0, 0, 0
    )
    time.sleep(20)

    # clear old MAVLink messages after reboot to see if fix bug
    while master.recv_match(blocking=False):
        pass


    master.mav.command_long_send(
        master.target_system, 
        master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 
        0,
        147,
        500000,
        0, 0, 0, 0, 0
    )

    received_batt8 = False
    received_batt9 = False

    #####*****CHANGES*****#####
    # Second hang that was in here: this was `while True` with
    # recv_match(blocking=True) and no timeout, so if the FC came back from the
    # reboot without sending BATTERY_STATUS this looped forever - the heartbeat
    # timeout above would not have saved us. Now it is bounded, and the
    # pre-seeded -1s mean the "no reading" case returns the same failure signal
    # as a failed param write instead of raising UnboundLocalError.
    voltage8 = -1
    voltage9 = -1
    deadline = time.time() + BATT_STATUS_TIMEOUT_S

    while time.time() < deadline:
        msg = master.recv_match(type='BATTERY_STATUS', blocking=True, timeout=1)

        if msg:
            if msg.id == 7:
                voltage8 = msg.voltages[0]/1000
                received_batt8 = True

            elif msg.id == 8:
                voltage9 = msg.voltages[0]/1000
                received_batt9 = True

            else:
                received_batt8 = True
                received_batt9 = True
                voltage8 = -1
                voltage9 = -1

        if received_batt9 and received_batt8:
            break

    if not (received_batt8 and received_batt9):
        print(f"[ANALOG PORT] no BATTERY_STATUS for both channels in "
              f"{BATT_STATUS_TIMEOUT_S} s (batt8={received_batt8}, "
              f"batt9={received_batt9})")
    #####*****END CHANGES*****#####

    return [voltage8, voltage9]
