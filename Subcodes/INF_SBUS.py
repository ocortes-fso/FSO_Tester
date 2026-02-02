import time
import lgpio

# ---------------- CONFIG ---------------- #

SBUS_GPIO = 15          # GPIO pin for SBUS
SBUS_CHIP = 4           # GPIO chip index
BIT_TIME_US = 10
SBUS_FRAME_LENGTH = 25

PWM_MIN = 1000
PWM_MAX = 2000
SBUS_MIN = 172
SBUS_MAX = 1811

# -------------- GLOBALS ---------------- #

_h = None


# -------------- GPIO INIT --------------- #

def init_gpio():
    global _h
    if _h is None:
        _h = lgpio.gpiochip_open(SBUS_CHIP)
        lgpio.gpio_claim_input(_h, SBUS_GPIO)


def close_gpio():
    global _h
    if _h is not None:
        lgpio.gpiochip_close(_h)
        _h = None


# -------------- UTILITIES --------------- #

def sbus_to_pwm(val):
    val = max(SBUS_MIN, min(SBUS_MAX, val))
    return int(
        (val - SBUS_MIN)
        * (PWM_MAX - PWM_MIN)
        / (SBUS_MAX - SBUS_MIN)
        + PWM_MIN
    )


# -------------- SBUS READ --------------- #

def read_sbus_byte(timeout=0.01):
    """Read one SBUS byte with timeout (non-blocking)."""
    start = time.time()

    # Wait for start bit
    while lgpio.gpio_read(_h, SBUS_GPIO) == 1:
        if time.time() - start > timeout:
            return None

    time.sleep(1.5 * BIT_TIME_US / 1_000_000)

    value = 0
    for i in range(8):
        bit = lgpio.gpio_read(_h, SBUS_GPIO)
        value |= (bit << i)
        time.sleep(BIT_TIME_US / 1_000_000)

    return value ^ 0xFF


def decode_sbus_channels(frame):
    ch = [0] * 8
    ch[0] = ((frame[1] | frame[2] << 8) & 0x07FF)
    ch[1] = ((frame[2] >> 3 | frame[3] << 5) & 0x07FF)
    ch[2] = ((frame[3] >> 6 | frame[4] << 2 | frame[5] << 10) & 0x07FF)
    ch[3] = ((frame[5] >> 1 | frame[6] << 7) & 0x07FF)
    ch[4] = ((frame[6] >> 4 | frame[7] << 4) & 0x07FF)
    ch[5] = ((frame[7] >> 7 | frame[8] << 1 | frame[9] << 9) & 0x07FF)
    ch[6] = ((frame[9] >> 2 | frame[10] << 6) & 0x07FF)
    ch[7] = ((frame[10] >> 5 | frame[11] << 3) & 0x07FF)
    return ch


def read_sbus_frame(timeout=0.5):
    """
    Attempts to read a full SBUS frame.
    Returns list of 8 PWM values or None if timeout.
    """
    buf = bytearray()
    start = time.time()

    while time.time() - start < timeout:
        byte = read_sbus_byte()
        if byte is None:
            continue

        buf.append(byte)

        if len(buf) >= SBUS_FRAME_LENGTH:
            frame = buf[:SBUS_FRAME_LENGTH]
            raw = decode_sbus_channels(frame)
            return [sbus_to_pwm(v) for v in raw]

    return None
