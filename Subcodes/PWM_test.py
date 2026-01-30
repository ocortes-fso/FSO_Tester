import lgpio
import time
from pymavlink import mavutil

# serial connection setup
serial_port = "/dev/ttyAMA10"
baud_rate = 115200
master = mavutil.mavlink_connection(serial_port, baud_rate)
master.wait_heartbeat()

# disable extra servo outputs (SERVO9–13)
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

# reboot autopilot to apply parameters
master.mav.command_long_send(
    master.target_system,
    master.target_component,
    mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
    0, 1, 0, 0, 0, 0, 0, 0
)

time.sleep(20)  # wait for reboot and PWM rail startup

# PWM GPIO pins
PWMs = [17, 18, 27, 23, 22]
High = 1900
Low = 1100
Tolerance = 250
Channels = [9, 10, 11, 12, 13]
output_matrix = [0]*len(Channels)
read_values = [0]*len(Channels)

# lgpio initialization
h = lgpio.gpiochip_open(4)
pwm_data = {}

def pwm_interrupt_handler(chip, gpio, level, tick):
    if level == 1:
        pwm_data[gpio]['start'] = tick
    elif level == 0 and pwm_data[gpio]['start'] > 0:
        duration_ns = (tick - pwm_data[gpio]['start']) & 0xFFFFFFFF
        duration_us = duration_ns / 1000
        if 500 < duration_us < 2500:
            pwm_data[gpio]['width'] = int(duration_us)

def setup_pwm_reader(pins):
    for pin in pins:
        pwm_data[pin] = {'start': 0, 'width': 0}
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_DOWN)
        lgpio.callback(h, pin, lgpio.BOTH_EDGES, pwm_interrupt_handler)

def read_pwm_values():
    return [pwm_data[pin]['width'] for pin in PWMs]

def set_servo_pwm(channel, PWM_Val):
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
        0, channel, PWM_Val, 0, 0, 0, 0, 0
    )

# main logic
setup_pwm_reader(PWMs)
print("Starting PWM verification...")

# set all channels HIGH
for i, channel in enumerate(Channels):
    set_servo_pwm(channel, High)
time.sleep(1.0)  # wait for multiple PWM cycles

# read all PWM widths
read_values = read_pwm_values()
for i, val in enumerate(read_values):
    if High - Tolerance <= val <= High + Tolerance:
        output_matrix[i] = 1
    else:
        output_matrix[i] = 0

print("-"*30)
print(f"PWM Output Matrix: {output_matrix}")
print(f"PWM Readings (us): {read_values}")

if output_matrix == [1]*len(Channels):
    print("PWM Test **PASS**")
else:
    print("PWM Test **FAIL**")

lgpio.gpiochip_close(h)
