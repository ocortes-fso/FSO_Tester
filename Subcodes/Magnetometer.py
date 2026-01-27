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
    bus.write_byte_data(ADDR, REG_CONTROL_2, 0x80)
    time.sleep(0.05)

    # OSR=512, RNG=8G, ODR=200Hz, MODE=continuous
    bus.write_byte_data(ADDR, REG_CONTROL_1, 0b11011101)
    time.sleep(0.1)

#below changed from previous console version to not have a while true loop since gui handles re-calling the function to update values

def read_mag_xyz(bus):
    data = bus.read_i2c_block_data(ADDR, REG_DATA, 6)
    x = to_s16((data[1] << 8) | data[0])
    y = to_s16((data[3] << 8) | data[2])
    z = to_s16((data[5] << 8) | data[4])
    return x, y, z

def main():
        with SMBus(BUS) as bus:
            init_qmc5883l(bus)
            x, y, z = read_mag_xyz(bus)
            b = math.sqrt(x*x + y*y + z*z)
            return [x, y, z, b]
  
