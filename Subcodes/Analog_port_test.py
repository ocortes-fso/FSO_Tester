import time
from pymavlink import mavutil

#need to add voltage divider inside the DSUB cap

def analog_port_run():
    serial_port = "/dev/ttyAMA10" #debug port
    baud_rate = 115200

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
    master.wait_heartbeat()

    for name, value in Param_set.items():
        master.mav.param_set_send(
            master.target_system,
            master.target_component,
            name.encode('utf-8'),
            value,
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
        )
        time.sleep(0.02)

    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
        0,
        1,
        0, 0, 0, 0, 0, 0
    )
    time.sleep(15)

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

    while True:
        msg = master.recv_match(type='BATTERY_STATUS', blocking=True)
        
        if msg:
            if msg.id == 7:
                time.sleep(0.5)
                voltage8 = msg.voltages[0]/1000
                received_batt8 = True
            
            elif msg.id == 8:
                time.sleep(0.5)
                voltage9 = msg.voltages[0]/1000
                received_batt9 = True

        if received_batt9 and received_batt8:
            break

    return [voltage8, voltage9]
