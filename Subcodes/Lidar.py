##### LIDAR TEST USING I2C #####
## Requirements:
#   Need to enable I2C on the Raspberry PI
#   Need to have "smbus" library installed for I2C communication in Python
#       on windows, need to use 'smbus2'

### CONFIG ###
from smbus2 import SMBus  # Change this line to "import smbus" if in Linux based
import time

### Params ###
Lidar_ADDR = 0x66         # 0x66 (Hex) / 102 (Dec) 
I2C_BUS = 1               # Bus
DIST_REG = 0x00           # Need to confirm this, 00, 10, and 20 are common

### Show distance read by the LIDAR
with SMBus(I2C_BUS) as bus:
    print("Reading LW20 distance...")
    while True:
        try:
            data = bus.read_i2c_block_data(ADDR, DIST_REG, 2)

            # Big-endian (most common)
            dist = (data[0] << 8) | data[1]

            print(f"Distance: {dist}mm")
            time.sleep(0.1)

        except OSError as e:
            print("I2C error:", e)
            time.sleep(1)