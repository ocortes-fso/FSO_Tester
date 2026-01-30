from lgpio import *
import time

SBUS_GPIO = 15
SBUS_CHIP = 4
BIT_TIME_US = 10
SBUS_FRAME_LENGTH = 25
SBUS_HEADER = 0x0F

chip_handle = lgGpiochipOpen(SBUS_CHIP)
alert_handle = lgGpioClaimAlert(chip_handle, 0, LG_BOTH_EDGES, SBUS_GPIO, -1)

def read_sbus_byte():
    while lgGpioRead(chip_handle, SBUS_GPIO) == 0:
        pass
    time.sleep(1.5 * BIT_TIME_US / 1_000_000)
    value = 0
    for i in range(8):
        bit = lgGpioRead(chip_handle, SBUS_GPIO)
        value |= (bit << i)
        time.sleep(BIT_TIME_US / 1_000_000)
    time.sleep(3 * BIT_TIME_US / 1_000_000)
    return value ^ 0xFF

def read_sbus_frame():
    return bytes(read_sbus_byte() for _ in range(SBUS_FRAME_LENGTH))

try:
    while True:
        frame = read_sbus_frame()
        if len(frame) == SBUS_FRAME_LENGTH and frame[0] == SBUS_HEADER:
            print("SBUS Connected **PASS**")
        else:
            print("SBUS not detected **FAIL**")
except KeyboardInterrupt:
    pass
finally:
    lgGpioClose(chip_handle)
