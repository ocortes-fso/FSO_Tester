import time
import math
from smbus2 import SMBus

BUS = 1
ADDR = 0x1E

def read_u8(bus, reg):
    return bus.read_byte_data(ADDR, reg)

def read_s16_be(bus, reg):
    hi = read_u8(bus, reg)
    lo = read_u8(bus, reg + 1)
    v = (hi << 8) | lo
    return v - 65536 if v >= 32768 else v

def init_hmc5883l(bus):
    bus.write_byte_data(ADDR, 0x00, 0x70)  # Config A
    bus.write_byte_data(ADDR, 0x01, 0x20)  # Config B
    bus.write_byte_data(ADDR, 0x02, 0x00)  # continuous mode
    time.sleep(0.1)

def read_mag_xyz(bus):
    x = read_s16_be(bus, 0x03)
    z = read_s16_be(bus, 0x05)
    y = read_s16_be(bus, 0x07)
    return x, y, z

def clear():
    print("\033[2J\033[H", end="")  # clear screen + home cursor

def main():
    with SMBus(BUS) as bus:
        # ID check
        try:
            ida = read_u8(bus, 0x0A)
            idb = read_u8(bus, 0x0B)
            idc = read_u8(bus, 0x0C)
            ident = f"{chr(ida)}{chr(idb)}{chr(idc)}"
        except OSError as e:
            print("I2C error:", e)
            print("Check wiring and i2cdetect -y 1 (should show 0x1E).")
            return

        init_hmc5883l(bus)

        # baseline magnitude
        samples = []
        t0 = time.time()
        while time.time() - t0 < 1.0:
            x, y, z = read_mag_xyz(bus)
            samples.append(math.sqrt(x*x + y*y + z*z))
            time.sleep(0.05)
        base = sum(samples) / len(samples)
        thresh = 80.0

        last = None

        clear()
        print("Magnetometer Test (HMC5883L / GY-271)")
        print("Press Ctrl+C to exit.\n")
        print(f"I2C addr: {hex(ADDR)}")
        print(f"ID: {ident} (expected H43)\n")
        print("Live data:\n")

        while True:
            x, y, z = read_mag_xyz(bus)
            b = math.sqrt(x*x + y*y + z*z)

            dx = dy = dz = 0
            if last:
                dx, dy, dz = x-last[0], y-last[1], z-last[2]
            last = (x, y, z)

            moving = abs(b - base) > thresh

            clear()
            print("Magnetometer Test (HMC5883L / GY-271)")
            print("Ctrl+C to return.\n")
            print(f"ID: {ident} (expected H43)")
            print(f"Baseline |B|: {base:.1f}  Threshold: {thresh:.1f}\n")

            print(f"X: {x:7d}   Δ{dx:+6d}")
            print(f"Y: {y:7d}   Δ{dy:+6d}")
            print(f"Z: {z:7d}   Δ{dz:+6d}")
            print(f"|B|: {b:7.1f}")
            print(f"Movement: {'DETECTED' if moving else 'still'}\n")

            print("Tip: rotate the sensor; X/Y/Z should change.")
            time.sleep(0.1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
