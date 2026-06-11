# reads battery, temperature and current from INA228 sensor across the shunt resitor

#maybe consider extra data to show or not show and set limits with warnings ect. Wanted to add temp just to test the chip

from smbus2 import SMBus  
import time

ADDR = 0x41               # 0x41 (Hex) 
I2C_BUS = 1              

# INA228 Registers 
VBUS_REG = 0x05           # Bus Voltage Register address
VSHUNT_REG = 0x04         # Shunt Voltage Drop Register address
TEMP_REG = 0x06           # Temperature Register address
R_SHUNT = 0.0001          # Shunt resistor value in ohms 

VOLT_SF = 0.0001953125       # Voltage LSB in volts (195.3125 microvolts per bit) SF to double check
SHUNT_V_SF = 0.0000003125         # Shunt Voltage LSB in volts (3.125 microvolts per bit) SF to double check
TEMP_SF = 0.0078125          # Temperature LSB in degrees Celsius (7.8125 mC per bit) SF to double check


_bus = None

#create/open i2c bus
def _get_bus():
    global _bus
    if _bus is None:
        _bus = SMBus(I2C_BUS)
    return _bus

#voltage read
def read_battery_voltage():
    try:
        bus = _get_bus()
        data = bus.read_i2c_block_data(ADDR, VBUS_REG, 3)

    
        raw_value = (data[0] << 16) | (data[1] << 8) | data[2]
        vbus_raw = raw_value >> 4

        return vbus_raw * VOLT_SF

    except OSError:
        close()
        return None
    except Exception:
        close()
        return None

#current read
def read_battery_current():
    try:
        bus = _get_bus()
        data = bus.read_i2c_block_data(ADDR, VSHUNT_REG, 3)

        # Big-endian reconstruction (24-bit compilation)
        raw_value = (data[0] << 16) | (data[1] << 8) | data[2]
        vshunt_raw = raw_value >> 4
        
        # test if charge or discharge (negative or positive current) and convert from 2's complement if needed
        if vshunt_raw & (1 << 19):
            vshunt_raw -= (1 << 20)
            
        shunt_voltage_volts = vshunt_raw * SHUNT_V_SF
        
        #determine current using Ohm's Law: I = V / R
        return shunt_voltage_volts / R_SHUNT

    except OSError:
        close()
        return None
    except Exception:
        close()
        return None
    
#temperature read
def read_battery_temperature():
    try:
        bus = _get_bus()
        data = bus.read_i2c_block_data(ADDR, TEMP_REG, 2)

        # Big-endian reconstruction (16-bit compilation)
        temp_raw = (data[0] << 8) | data[1]
            
        # return deg C
        return temp_raw * TEMP_SF
    
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