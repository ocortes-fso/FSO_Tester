import RPi.GPIO as GPIO
import time
from pymavlink import mavutil

#need serial connection to write params (servo functions)

serial_port = "/dev/ttyAMA0" #GPIO pin serial port may need to config boot config file to enable
baud_rate = 57600 #again confirm this is correct serial 5 baud rate
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
        time.sleep(0.02)
        
    )


#send reboot command

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
    0  
)

time.sleep(5) #may need longer here...

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
Pass_status = [1,1,1,1,1] #create pass status list array - numpy might be better to use here 
output_matrix = [0,0,0,0,0]


#read PWM function/(s) 

pwm_data = {}

def pwm_interrupt_handler(channel):
    current_time = time.time()
    if GPIO.input(channel):
        # Signal went HIGH - start the stopwatch
        pwm_data[channel]['start'] = current_time
    else:
        # Signal went LOW - stop the stopwatch and calculate width
        if pwm_data[channel]['start'] > 0:
            duration = (current_time - pwm_data[channel]['start']) * 1000000
            pwm_data[channel]['width'] = int(duration)

def setup_pwm_reader(pins):
    GPIO.setmode(GPIO.BCM)
    for pin in pins:
        pwm_data[pin] = {'start': 0, 'width': 0}
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        # Monitor BOTH rising and falling edges
        GPIO.add_event_detect(pin, GPIO.BOTH, callback=pwm_interrupt_handler)

def read_pwm_values(pin):
    return pwm_data[pin]['width']


#Function to set PWM/servo outputs on autopilot via MAVLink
def set_servo_pwm(channel, PWM_Val):
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
        0,                 #confirmation 
        channel,            # servo/channel number
        PWM_Val,            # PWM in microseconds (e.g. 1100 or 1900)
        0, 0, 0, 0, 0       #set unused parameters to 0  ---- https://ardupilot.org/copter/docs/common-mavlink-mission-command-messages-mav_cmd.html#mav-cmd-do-set-servo
    )

#main logic

#loop through each PWM channel and set 1 by 1 to high and others low, and read PWM on GPIO the current GPIO pin for that channel

PWM_Val = {}
setup_pwm_reader(PWMs)

for current_PWM in range(len(Channels)):
    for i in range(len(Channels)):
        PWM_Val = High if i == current_PWM else Low
        set_servo_pwm(Channels[i], PWM_Val)
        PWM_output = read_pwm_values(PWMs[i])
        
        #check PWM output is within range +/- tolerance and output to array (1 is pass, 0 is fail)
        
        if PWM_output <= High + Tolerance and PWM_output >= High - Tolerance:
            output_matrix[i] = 1
        else:
            output_matrix[i] = 0
            
#final check against pass condition      
if output_matrix == Pass_status:
    print("PWM Test **PASS**") 
else:
    print("PWM Test **FAIL**")  
    
GPIO.cleanup()     

