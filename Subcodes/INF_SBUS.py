import time
import lgpio

# Handle moved outside to prevent re-opening every call
h = None

def sbus_inf():
    global h
    # ---------------- CONFIG ---------------- #

    SBUS_GPIO = 15
    SBUS_CHIP = 4
    BIT_TIME_US = 10
    SBUS_FRAME_LENGTH = 25

    PWM_MIN = 1000
    PWM_MAX = 2000
    SBUS_MIN = 172
    SBUS_MAX = 1811

    # -------------- GPIO INIT -------------- #

    if h is None:
        try:
            h = lgpio.gpiochip_open(SBUS_CHIP)
            lgpio.gpio_claim_input(h, SBUS_GPIO)
        except Exception:
            return None

    # -------------- HELPERS ---------------- #

    def sbus_to_pwm(val):
        val = max(SBUS_MIN, min(SBUS_MAX, val))
        return int(
            (val - SBUS_MIN)
            * (PWM_MAX - PWM_MIN)
            / (SBUS_MAX - SBUS_MIN)
            + PWM_MIN
        )

    def read_sbus_byte(timeout=0.02):
        start = time.time()

        while lgpio.gpio_read(h, SBUS_GPIO) == 1:
            if time.time() - start > timeout:
                return None

        time.sleep(1.5 * BIT_TIME_US / 1_000_000)

        value = 0
        for i in range(8):
            value |= (lgpio.gpio_read(h, SBUS_GPIO) << i)
            time.sleep(BIT_TIME_US / 1_000_000)

        return value ^ 0xFF

    def decode(frame):
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

    # -------------- READ FRAME ------------- #

    buf = bytearray()
    start = time.time()

    # Reduced search window to 0.1s to prevent long GUI hangs
    while time.time() - start < 0.1:
        byte = read_sbus_byte()
        if byte is None:
            continue

        buf.append(byte)

        if len(buf) >= SBUS_FRAME_LENGTH:
            frame = buf[:SBUS_FRAME_LENGTH]
            pwm = [sbus_to_pwm(v) for v in decode(frame)]
            return pwm

    return None