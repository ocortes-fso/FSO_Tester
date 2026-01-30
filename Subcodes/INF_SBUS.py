import time
import lgpio
import sys

# -------- CONFIG --------
SBUS_GPIO = 15             # Pin for SBUS signal (GPIO15)
SBUS_CHIP = 4              # GPIO chip
BIT_TIME_US = 10           # Bit time in microseconds for SBUS
SBUS_FRAME_LENGTH = 25     # SBUS frame length in bytes
SBUS_HEADER = 0x0F         # SBUS header byte (not used here)

PWM_MIN = 1000             # Min PWM (µs) for channel values
PWM_MAX = 2000             # Max PWM (µs) for channel values
SBUS_MIN = 172             # SBUS raw min value for channel
SBUS_MAX = 1811            # SBUS raw max value for channel

UPDATE_PERIOD = 0.25       # Time delay between printing updates (in seconds)

# Open the GPIO chip and claim the SBUS GPIO for input
h = lgpio.gpiochip_open(SBUS_CHIP)
lgpio.gpio_claim_input(h, SBUS_GPIO)

def sbus_to_pwm(val):
    """Convert SBUS value to PWM (in microseconds)."""
    val = max(SBUS_MIN, min(SBUS_MAX, val))  # Clamp the value between min and max
    return int(
        (val - SBUS_MIN) * (PWM_MAX - PWM_MIN)
        / (SBUS_MAX - SBUS_MIN) + PWM_MIN
    )

def read_sbus_byte():
    """Reads one byte of SBUS data from the GPIO."""
    # Wait for the next transition to LOW (start bit)
    while lgpio.gpio_read(h, SBUS_GPIO) == 1:
        pass

    # Wait for the middle of the first data bit
    time.sleep(1.5 * BIT_TIME_US / 1_000_000)

    value = 0
    for i in range(8):
        bit = lgpio.gpio_read(h, SBUS_GPIO)
        value |= (bit << i)
        time.sleep(BIT_TIME_US / 1_000_000)  # Sleep between bits

    return value ^ 0xFF  # Invert the byte (software inversion)

def decode_sbus_channels(frame):
    """Decode the first 8 channels from the SBUS frame."""
    channels = [0] * 8
    channels[0] = ((frame[1] | frame[2] << 8) & 0x07FF)
    channels[1] = ((frame[2] >> 3 | frame[3] << 5) & 0x07FF)
    channels[2] = ((frame[3] >> 6 | frame[4] << 2 | frame[5] << 10) & 0x07FF)
    channels[3] = ((frame[5] >> 1 | frame[6] << 7) & 0x07FF)
    channels[4] = ((frame[6] >> 4 | frame[7] << 4) & 0x07FF)
    channels[5] = ((frame[7] >> 7 | frame[8] << 1 | frame[9] << 9) & 0x07FF)
    channels[6] = ((frame[9] >> 2 | frame[10] << 6) & 0x07FF)
    channels[7] = ((frame[10] >> 5 | frame[11] << 3) & 0x07FF)
    return channels

def main():
    buf = bytearray()  # Buffer to hold SBUS data
    last_print = 0     # Track the time of the last print

    print("Listening for SBUS...\n")

    try:
        while True:
            byte = read_sbus_byte()

            buf.append(byte)

            # If we have enough bytes, start decoding a frame
            if len(buf) >= SBUS_FRAME_LENGTH:
                frame = buf[:SBUS_FRAME_LENGTH]
                buf = buf[SBUS_FRAME_LENGTH:]

                # Decode the first 8 channels
                channels = decode_sbus_channels(frame)
                pwm = [sbus_to_pwm(v) for v in channels]

                # Print the decoded PWM values every UPDATE_PERIOD seconds
                now = time.time()
                if now - last_print >= UPDATE_PERIOD:
                    line = " ".join(f"C{i+1}={pwm[i]:4d}" for i in range(8))
                    sys.stdout.write("\r" + line)  # Print on the same line
                    sys.stdout.flush()
                    last_print = now

    except KeyboardInterrupt:
        pass
    finally:
        lgpio.gpiochip_close(h)

if __name__ == "__main__":
    main()
