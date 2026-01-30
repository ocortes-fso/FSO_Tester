import lgpio
import time
from pymavlink import mavutil

serial_port = "/dev/ttyAMA10"
baud_rate = 115200
master = mavutil.mavlink_connection(serial_port, baud_rate)
master.wait_heartbeat()

Param_set = {
    "SERVO9_FUNCTION": 0,
    "SERVO10_FUNCTION": 0,
    "SERVO11_FUNCTION": 0,
    "SERVO12_FUNCTION": 0,
    "SERVO13_FUNCTION": 0,
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

master.mav.command_long_send(
    master.target_system,
    master.target_component,
    mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
    0, 1, 0, 0, 0, 0, 0, 0
)

time.sleep(15)

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

print(final_values)

# Pass/fail check
if final_values == [High]*5:
    print("PWM Test **PASS**")
else:
    print("PWM Test **FAIL**")

lgpio.gpiochip_close(h)
