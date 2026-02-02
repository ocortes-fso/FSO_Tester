import time
import lgpio
import sys

SBUS_GPIO = 15             # Pin for SBUS signal (GPIO15)
SBUS_CHIP = 4               # GPIO chip
BIT_TIME_US = 10           # Bit time in microseconds for SBUS
SBUS_FRAME_LENGTH = 25     # SBUS frame length in bytes
SBUS_HEADER = 0x0F         # SBUS header byte (not used here)

PWM_MIN = 1000             # Min PWM (µs) for channel values
PWM_MAX = 2000             # Max PWM (µs) for channel values
SBUS_MIN = 172             # SBUS raw min value for channel
SBUS_MAX = 1811            # SBUS raw max value for channel

h = None

def sbus_to_pwm(val):
    val = max(SBUS_MIN, min(SBUS_MAX, val))  # Clamp the value between min and max
    return int(
        (val - SBUS_MIN) * (PWM_MAX - PWM_MIN)
        / (SBUS_MAX - SBUS_MIN) + PWM_MIN
    )

def read_sbus_byte():
    global h
    if h is None:
        h = lgpio.gpiochip_open(SBUS_CHIP)
        lgpio.gpio_claim_input(h, SBUS_GPIO)

    # Added timeout to prevent GUI hang
    start_time = time.time()
    while lgpio.gpio_read(h, SBUS_GPIO) == 1:
        if time.time() - start_time > 0.1: # 100ms timeout
            return 0

    time.sleep(1.5 * BIT_TIME_US / 1_000_000)

    value = 0
    for i in range(8):
        bit = lgpio.gpio_read(h, SBUS_GPIO)
        value |= (bit << i)
        time.sleep(BIT_TIME_US / 1_000_000)

    return value ^ 0xFF  # Invert the byte (software inversion)

def decode_sbus_channels(frame):
    channels = [0] * 8
    channels[0] = ((frame[1] | frame[2] << 8) & 0x07FF)
    channels[1] = ((frame[2] >> 3 | frame[3] << 5) & 0x07FF)
    channels[2] = ((frame[3] >> 6 | frame[4] << 2 | frame[5] << 10) & 0x07FF)
    channels[3] = ((frame[5] >> 1 | frame[6] << 7) & 0x07FF)
    channels[4] = ((frame[6] >> 4 | frame[7] << 4) & 0x07FF)
    channels[5] = ((