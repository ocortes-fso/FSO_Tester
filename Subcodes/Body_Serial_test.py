import time
from pymavlink import mavutil

#establish seral connection to autopilot via DSUB 

serial_port = "/dev/ttyAMA0" #debug serial port -- confirm this is correct
baud_rate = 57600 #again confirm this is correct serial 5 baud rate

#test for serial receive

master = mavutil.mavlink_connection(serial_port, baud_rate)
print ("waiting for heatbeart **CONNECTING**") 
time.sleep(1)
master.wait_heartbeat()
print("Heartbeat received from system (system %u)" % (master.target_system))


