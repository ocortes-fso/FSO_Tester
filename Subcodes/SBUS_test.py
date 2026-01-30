from lgpio import *
import time

SBUS_GPIO = 15
SBUS_CHIP = 4
BIT_TIME_US = 10
SBUS_FRAME_LENGTH = 25
SBUS_HEADER = 0x0F

chip_handle = lgGpiochipOpen(SBUS_CHIP)
lgGpioClaimInput(chip_handle, 0, SBUS_GPIO)

def read_sbus_byte():
    start_wait = time.time()
    while lgGpioRead(chip_handle, SBUS_GPIO) == 1:
        if time.time() - start_wait > 0.1: return None
    
    time.sleep(1.5 * BIT_TIME_US / 1_000_000)
    value = 0
    for i in range(8):
        bit = lgGpioRead(chip_handle, SBUS_GPIO)
        value |= (bit << i)
        time.sleep(BIT_TIME_US / 1_000_000)
    
    return value ^ 0xFF

def sync_sbus():
    # Wait for a 4ms gap of "High" (idle) to ensure we are at the start of a frame
    idle_start = time.time()
    while time.time() - idle_start < 0.004:
        if lgGpioRead(chip_handle, SBUS_GPIO) == 0:
            idle_start = time.time()

try:
    while True:
        sync_sbus() # Ensures we start at the Header
        frame = []
        for _ in range(SBUS_FRAME_LENGTH):
            b = read_sbus_byte()
            if b is not None: frame.append(b)
        
        if len(frame) == SBUS_FRAME_LENGTH and frame[0] == SBUS_HEADER:
            print("SBUS Connected **PASS**")
        else:
            print("SBUS not detected **FAIL**")
except KeyboardInterrupt:
    pass
finally:
    lgGpioClose(chip_handle)