import time
from pymavlink import mavutil

serial_port = "/dev/ttyAMA0" #GPIO pin serial port may need to config boot config file to enable
baud_rate = 57600 #again confirm this is correct serial 5 baud rate

Param_set = {
    "BATT8_OPTIONS": 1,
    "BATT8_MONITOR": 3,
    "BATT8_VOLT_PIN": 14,
    "BATT9_OPTIONS": 1,
    "BATT9_MONITOR": 3,
    "BATT9_VOLT_PIN": 15,

}

#send required params

master = mavutil.mavlink_connection(serial_port, baud_rate)
print ("waiting for heatbeart **CONNECTING**") 
time.sleep(1)
master.wait_heartbeat()
print("Heartbeat received from system (system %u)" % (master.target_system))


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

#request battery status..

master.mav.command_long_send(
    master.target_system, 
    master.target_component,
    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 
    0,
    147,      # Message ID for battery status
    500000,   # Interval in microseconds
    0, 0, 0, 0, 0
)

received_batt8 = False
received_batt9 = False

print("Waiting for Battery 8 and 9 status...")


while True:
    # Wait for the next BATTERY_STATUS message
    msg = master.recv_match(type='BATTERY_STATUS', blocking=True)
    
    if msg:
        # Check the 'id' field to find Battery 8 and 9 and print result for each
        
        if msg.id == 7:   #index starts at zero (n-1)
            voltag8 = msg.voltages[0]/1000 #convert from Mv to Volts
            print(f"BATT8 Status: {voltage8}")
            received_batt8 = True
        
        elif msg.id == 8:
            voltage9 = msg.voltages[0]/1000
            print(f"BATT9 Status: {voltage9}")
            received_batt9 = True
    if received_batt9 and received_batt8:
        break
    

if (1 <= voltag8 <= 1.5) and (2.25<= voltage9 <= 2.75):
    print("Analog Voltage Pass!")
else:
    print("Analog Voltage Fail!")



# turn off parmeters can be done in final UI sends all paramters at end of main body test to defualts 
            
        
            
