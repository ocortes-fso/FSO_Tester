import can
import time
import os

CAN_INTERFACE = 'can0'  # Interface name (adjust if needed)
BITRATE = 500000  # Ensure this matches the flight controller's CAN bitrate
TIMEOUT = 5  # Time in seconds to wait for a response

#Set up the CAN interface (ensure CAN bus is running)
os.system(f"sudo ip link set {CAN_INTERFACE} down")  # Bring CAN interface down
os.system(f"sudo ip link set {CAN_INTERFACE} up type can bitrate {BITRATE}")  # Set bitrate and bring CAN interface up
time.sleep(0.5)

#Initialize CAN bus interface (debugging can remove this when all wokring)
try:
    canbus = can.interface.Bus(channel=CAN_INTERFACE, bustype='socketcan')
    print(f"CAN interface {CAN_INTERFACE} set up with bitrate {BITRATE}")
except can.CanError:
    print(f"Error: CAN interface {CAN_INTERFACE} is not working properly.")
    exit(1)

#Listen for CAN messages
print(f"Listening for CAN messages on {CAN_INTERFACE}...")
msg_rx = canbus.recv(timeout=TIMEOUT)  # Wait up to 5 seconds for a message

#Check if any messages were received and print
if msg_rx:
    print(f"CAN check PASS!! Received message: {msg_rx}")
else:
    print("CAN check FAIL: No message received")
