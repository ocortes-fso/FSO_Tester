##We will need to add the kernel level driver to the boot config file, there is a standard overlay driver for the can bus chip we are using mcp2515

import can
import time
import os

#send bash cmds to setup can interface

os.system("sudo ip link set can0 down")
os.system("sudo ip link set can0 up type can bitrate 500000 loopback on")  #is this bitratte fine? does this need to match the aircraft can rate... #loopback on for testing own node

time.sleep(0.5)

#main logic

canbus = can.interface.Bus(channel='can0', bustype='socketcan')


#send can message to bus
msg_tx = can.Message(arbitration_id=0x123, data=[0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88], is_extended_id=False)
print("sending CAN mesasage...")
canbus.send(msg_tx)

time.sleep(0.5)


#recieve can message on same bus
print("receiving CAN message...")
msg_rx = canbus.recv(timeout=5)  

if msg_rx: 
    print ("CAN check PASS!!:")
else :
    print("CAN check FAIL: No message received")


