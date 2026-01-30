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
Tolerance = 200
Channels = [9, 10, 11, 12, 13] 
Pass_status = [1, 1, 1, 1, 1] 
output_matrix = [0, 0, 0, 0, 0]
read_values = [0, 0, 0, 0, 0]

h = lgpio.gpiochip_open(4)
pwm_data = {}

def pwm_interrupt_handler(chip, gpio, level, tick):
    if level == 1:
        pwm_data[gpio]['start'] = tick
    elif level == 0:
        if pwm_data[gpio]['start'] > 0:
            duration_ns = (tick - pwm_data[gpio]['start']) & 0xFFFFFFFF
            duration_us = duration_ns / 1000
            if 500 < duration_us < 2500:
                pwm_data[gpio]['width'] = int(duration_us)

def setup_pwm_reader(pins):
    for pin in pins:
        pwm_data[pin] = {'start': 0, 'width': 0}
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_DOWN)
        lgpio.gpio_claim_alert(h, pin, lgpio.BOTH_EDGES)
        lgpio.callback(h, pin, lgpio.BOTH_EDGES, pwm_interrupt_handler)

def read_pwm_values(pin):
    return pwm_data[pin]['width']

def set_servo_pwm(channel, PWM_Val):
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
        0, channel, PWM_Val, 0, 0, 0, 0, 0
    )

setup_pwm_reader(PWMs)

for current_PWM in range(len(Channels)):
    for pin in PWMs:
        pwm_data[pin]['width'] = 0
        pwm_data[pin]['start'] = 0

    for i in range(len(Channels)):
        target_val = High if i == current_PWM else Low
        set_servo_pwm(Channels[i], target_val)
        time.sleep(0.05)

    time.sleep(0.5)

    for idx, pin in enumerate(PWMs):
        _ = read_pwm_values(pin)

    read_values[current_PWM] = read_pwm_values(PWMs[current_PWM])

    if High - Tolerance <= read_values[current_PWM] <= High + Tolerance:
        output_matrix[current_PWM] = 1
    else:
        output_matrix[current_PWM] = 0

print(f"Final Output Matrix: {output_matrix}")
print(f"Final PWM Readings (us): {read_values}")

if output_matrix == Pass_status:
    print("PWM Test **PASS**") 
else:
    print("PWM Test **FAIL**")  
    
lgpio.gpiochip_close(h)
