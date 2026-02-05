import can
import time
import os

def run_can():
    CAN_INTERFACE = 'can0'  # Interface name (adjust if needed)
    BITRATE = 1000000  # Ensure this matches the flight controller's CAN bitrate
    TIMEOUT = 5  # Time in seconds to wait for a response
    #Set up the CAN interface (ensure CAN bus is running)
    os.system(f"sudo ip link set {CAN_INTERFACE} down")  # Bring CAN interface down
    os.system(f"sudo ip link set {CAN_INTERFACE} up type can bitrate {BITRATE}")  # Set bitrate and bring CAN interface up
    time.sleep(0.5)

    #Initialize CAN bus interface (debugging can remove this when all wokring)

    canbus = can.interface.Bus(channel=CAN_INTERFACE, interface='socketcan')

    msg_rx = canbus.recv(timeout=TIMEOUT)  # Wait up to 5 seconds for a message

        #Check if any messages were received and print
    status =  None

    if msg_rx:
        status = True
    else:
        print("CAN check FAIL: No message received")
        status = False

    return status

    # Shut down bus 
    os.system(f"sudo ip link set {CAN_INTERFACE} down")  # Bring CAN interface down
    canbus.shutdown()


