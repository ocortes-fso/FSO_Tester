import time
from pymavlink import mavutil

#establish seral connection to autopilot via DSUB 

serial_port = "/dev/ttyAMA10" #GPIO pin serial port may need to config boot config file to enable
baud_rate = 57600 #again confirm this is correct serial 5 baud rate

#test for serial receive changed to function for GUI

def serial_test():
    #####*****CHANGES*****#####
    # The connection is now CLOSED before returning. It used to be left open,
    # and the three subcodes that run after this one each open the same
    # /dev/ttyAMA10 again - pyserial takes no exclusive lock by default, so two
    # live readers on one tty split the byte stream between them and both see
    # corrupt MAVLink. CPython's reference counting usually freed this one on
    # return, which is why it mostly worked, but that is luck rather than
    # design and it is the first thing to suspect when the link looks flaky.
    master = mavutil.mavlink_connection(serial_port, baud_rate)
    try:
        time.sleep(1)
        return bool(master.wait_heartbeat(timeout=5))
    finally:
        try:
            master.close()
        except Exception as e:
            print(f"[SERIAL] close: {e}")
    #####*****END CHANGES*****#####
    
    
