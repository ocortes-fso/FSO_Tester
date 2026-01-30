import lgpio
import time
from pymavlink import mavutil

#need serial connection to write params (servo functions)

serial_port = "/dev/ttyAMA10" #GPIO pin serial port may need to config boot config file to enable
baud_rate = 115200 #again confirm this is correct serial 5 baud rate
master = mavutil.mavlink_connection(serial_port, baud_rate)
master.wait_heartbeat()

#servo PWM channel paramters -- set to disabled
Param_set = {
    "SERVO9_FUNCTION": 0,
    "SERVO10_FUNCTION": 0,
    "SERVO11_FUNCTION": 0,
    "SERVO12_FUNCTION": 0,
    "SERVO13_FUNCTION": 0,
}

#send parms to autopilot -- looping through each one with a small delay..

for name, value in Param_set.items():
    master.mav.param_set_send(
        master.target_system,
        master.target_component,
        name.encode('utf-8'), 
        value,                
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32,    
    )
    time.sleep(0.02)

#send reboot command
print("Rebooting")

master.mav.command_long_send(
    master.target_system,
    master.target_component,
    mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
    0, # Confirmation
    1, # param1: 1 = Reboot
    0, 
    0, 
    0, 
    0, 
    0,
    0 
)

time.sleep(15) 

#GPIO pin setup

PWM_1 = 17
PWM_2 = 18
PWM_3 = 27
PWM_4 = 23
PWM_5 = 22
PWMs = [PWM_1, PWM_2, PWM_3, PWM_4, PWM_5]

#Define conditions
High = 1900
Low = 1100
Tolerance = 200
Channels = [9,10,11,12,13] #actual RC servo channels 
Pass_status = [1,1,1,1,1] 
output_matrix = [0,0,0,0,0]
read_values = [0,0,0,0,0] # Added to store the raw PWM readings

# lgpio handle initialization
h = lgpio.gpiochip_open(4)

#read PWM function/(s) 

pwm_data = {}

def pwm_interrupt_handler(chip, gpio, level, tick):
    if level == 1:
        pwm_data[gpio]['start'] = tick
    elif level == 0:
        if pwm_data[gpio]['start'] > 0:
            duration = tick - pwm_data[gpio]['start']
            if duration < 0: duration += 4294967296
            pwm_data[gpio]['width'] = int(duration)

def setup_pwm_reader(pins):
    for pin in pins:
        pwm_data[pin] = {'start': 0, 'width': 0}
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_DOWN)
        lgpio.gpio_claim_alert(h, pin, lgpio.BOTH_EDGES)
        lgpio.callback(h, pin, lgpio.BOTH_EDGES, pwm_interrupt_handler)

def read_pwm_values(pin):
    return pwm_data[pin]['width']

#Function to set PWM/servo outputs on autopilot via MAVLink
def set_servo_pwm(channel, PWM_Val):
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
        0,                 
        channel,            
        PWM_Val,            
        0, 0, 0, 0, 0       
    )

#main logic

setup_pwm_reader(PWMs)

for current_PWM in range(len(Channels)):
    for i in range(len(Channels)):
        target_val = High if i == current_PWM else Low
        set_servo_pwm(Channels[i], target_val)
    
    time.sleep(0.5)
    
    PWM_output = read_pwm_values(PWMs[current_PWM])
    read_values[current_PWM] = PWM_output # Store raw microsecond value
    
    if PWM_output <= High + Tolerance and PWM_output >= High - Tolerance:
        output_matrix[current_PWM] = 1
    else:
        output_matrix[current_PWM] = 0

# One-time output of both results
print(f"Final Output Matrix: {output_matrix}")
print(f"Final PWM Readings (us): {read_values}")

#final check against pass condition      
if output_matrix == Pass_status:
    print("PWM Test **PASS**") 
else:
    print("PWM Test **FAIL**")  
    
lgpio.gpiochip_close(h)