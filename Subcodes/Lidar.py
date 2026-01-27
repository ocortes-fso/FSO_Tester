##### LIDAR TEST USING I2C #####
## Requirements:
#   Need to enable I2C on the Raspberry PI

### CONFIG ###
from smbus2 import SMBus  
import time

### Params ###
ADDR = 0x66               # 0x66 (Hex) / 102 (Dec) 
I2C_BUS = 1               # Bus
DIST_REG = 0x00           # Need to confirm this, 00, 10, and 20 are common

### Show distance read by the LIDAR, below changed from older commit to allow for GUI use --removed while true and return distance value
def read_lidar_distance():
    with SMBus(I2C_BUS) as bus:
        try:
            data = bus.read_i2c_block_data(ADDR, DIST_REG, 2)

            # Big-endian (most common)
            dist = (data[0] << 8) | data[1] #mm output 
            dist_m = dist / 1000.0  # Convert to meters
            return dist_m

        except OSError:
            return None