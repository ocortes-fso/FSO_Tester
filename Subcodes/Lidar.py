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

_bus = None

### Show distance read by the LIDAR, below changed from older commit to allow for GUI use --removed while true and return distance value
def _get_bus():
    global _bus
    if _bus is not None:
        try:
            _bus.close()
        finally:
            _bus = None

def read_lidar_distance():
    try:
        bus = _get_bus()
        data = bus.read_i2c_block_data(ADDR, DIST_REG, 2)

        # Big-endian (most common)
        dist_mm = (data[0] << 8) | data[1] # mm output 
        return dist_mm / 1000.0

    except OSError:
        close()
        return None
    except Exception:
        close()
        return None
        
def close():
    global _bus
    if _bus is not None:
        try:
            _bus.close()
        finally:
            _bus = None
