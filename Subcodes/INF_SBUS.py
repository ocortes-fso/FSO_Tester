import serial
import time
import sys

# -------- CONFIG --------
PORT = "/dev/ttyAMA0"   # Pi 5 debug UART
BAUD = 100000 #double check this is fine for SBUS
UPDATE_PERIOD = 0.25   # seconds delay between updating output 

SBUS_MIN = 172
SBUS_MAX = 1811
PWM_MIN = 1000.    #i think the rznge is slighly less 1950 or somewhitng need to confirm rhis 
PWM_MAX = 2000
# ------------------------

def sbus_to_pwm(val):
    val = max(SBUS_MIN, min(SBUS_MAX, val))
    return int(
        (val - SBUS_MIN) * (PWM_MAX - PWM_MIN)
        / (SBUS_MAX - SBUS_MIN)
        + PWM_MIN
    )

def decode_sbus_channels(frame):
    """Decode first 8 SBUS channels from 25-byte frame -- INF test is only first 8 channels if all wokring"""
    ch = [0] * 8

    ch[0] = ((frame[1]     | frame[2] << 8) & 0x07FF)
    ch[1] = ((frame[2] >> 3 | frame[3] << 5) & 0x07FF)
    ch[2] = ((frame[3] >> 6 | frame[4] << 2 | frame[5] << 10) & 0x07FF)
    ch[3] = ((frame[5] >> 1 | frame[6] << 7) & 0x07FF)
    ch[4] = ((frame[6] >> 4 | frame[7] << 4) & 0x07FF)
    ch[5] = ((frame[7] >> 7 | frame[8] << 1 | frame[9] << 9) & 0x07FF)
    ch[6] = ((frame[9] >> 2 | frame[10] << 6) & 0x07FF)
    ch[7] = ((frame[10] >> 5 | frame[11] << 3) & 0x07FF)

    return ch

def main():
    ser = serial.Serial(
        PORT,
        BAUD,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_TWO,
        timeout=0.1,
    )

    buf = bytearray()
    last_print = 0

    print("Listening for SBUS...\n")

    while True:
        buf += ser.read(ser.in_waiting or 1)

        while len(buf) >= 25:
            if buf[0] != 0x0F:  # SBUS start byte
                buf.pop(0)
                continue

            frame = buf[:25]
            buf = buf[25:]

            channels = decode_sbus_channels(frame)
            pwm = [sbus_to_pwm(v) for v in channels]

            now = time.time()
            if now - last_print >= UPDATE_PERIOD:
                line = " ".join(f"C{i+1}={pwm[i]:4d}" for i in range(8))
                sys.stdout.write("\r" + line)
                sys.stdout.flush()
                last_print = now

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
