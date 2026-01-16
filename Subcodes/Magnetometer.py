import time
import math
from smbus2 import SMBus

BUS = 1
ADDR = 0x0D

# QMC5883L registers
REG_DATA = 0x00
REG_STATUS = 0x06
REG_CONTROL_1 = 0x09
REG_CONTROL_2 = 0x0A

def to_s16(v):                 # Limit big-endian 16-bit
    return v - 65536 if v >= 32768 else v

def init_qmc5883l(bus):                    # Initialize Magnetometer
    # Reset
    bus.write_byte_data(ADDR, REG_CONTROL_2, 0x80)  
    time.sleep(0.05)

    # Control 1
    # OSR=512 (11), RNG=8G (01), ODR=200Hz (11), MODE=continuous (01)
    bus.write_byte_data(ADDR, REG_CONTROL_1, 0b11011101)
    time.sleep(0.5)

def read_mag_xyz(bus):
    data = bus.read_i2c_block_data(ADDR, REG_DATA, 6)
    # QMC5883L is LITTLE-endian: LSB first
    x = to_s16((data[1] << 8) | data[0])
    y = to_s16((data[3] << 8) | data[2])
    z = to_s16((data[5] << 8) | data[4])
    return x, y, z

def main():
    with SMBus(BUS) as bus:
        init_qmc5883l(bus)

        # baseline magnitude
        samples = []
        t0 = time.time()
        while time.time() - t0 < 1.0:
            x, y, z = read_mag_xyz(bus)
            samples.append(math.sqrt(x*x + y*y + z*z))
            time.sleep(0.05)
        base = sum(samples) / len(samples)

        thresh = 200.0
        last = None

        # Show data
        #print("\033[2J\033[H", end="")
        #print("Magnetometer Test (QMC5883L)")
        #print("Press Ctrl+C to exit.\n")
        #print(f"I2C addr: {hex(ADDR)}")
        #print("Live data:\n")

        #print("t(s)     X      Y      Z     |B|")
        t_start = time.time()

        while True:
            x, y, z = read_mag_xyz(bus)
            b = math.sqrt(x*x + y*y + z*z)
            t = time.time() - t_start
            #print(f"{t:6.1f}  {x:6d} {y:6d} {z:6d}  {b:7.1f}")
            time.sleep(0.2)

    return [x, y, z, b]

""" if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
 """