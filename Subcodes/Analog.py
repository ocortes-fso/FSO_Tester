import time 
import smbus2  #this package is only for linux will work on pi but cannot isntall on windows 

#define variables

I2C_ADD = 1000101  #all  pins left floating (not connected)
I2C_bus = smbus2.SMBus(1)
Voltage_ref = float(3.3)
ADC_raw_factor = float(65535) #float to to find output relative to reference (STANDARD ADC for 16-bit resolution)

#from voltage dividers on PCB  (Rbot/(rbot+rtop))
DIV_12V = 0.2448
DIV_5V = 0.5
DIV_50V = 0.032

#define used channels for each DSUB

Channels_DSUB1 = [0xB8, 0xB1] #used channels in hex
Channels_DSUB2 = [0xB2, 0xBA] #used channels in hex
Channels_DSUB3A = [0xBB, 0xB4] #used channels in hex
Channels_DSUB3B = [0xB5, 0xBD] #used channels in hex
Channels_DSUB_Power = 0xBE #used channels in hex

#define functions 

def DSUB1():
    channel = Channels_DSUB1[0]
    bus.write_byte(I2C_ADD, channel)   # send address byte for channel 
    time.sleep(0.02)
    output = bus.read_i2c_block_data(I2C_ADD, channel, 3) #read ouput raw data from 3 bytes
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6) #extract 16 bit value from 3 bytes
    voltage = float(Voltage_ref*raw_val/ADC_raw_factor)/DIV_12V #convert 16 bit to voltage against reference VVC voltage
    print (voltage)
    channel = Channels_DSUB1[1]
    bus.write_byte(I2C_ADD, channel)   # send address byte for channel 
    output = bus.read_i2c_block_data(I2C_ADD, channel, 3) #read ouput raw data from 3 bytes
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6) #extract 16 bit value from 3 bytes
    voltage2 = float(Voltage_ref*raw_val/ADC_raw_factor)/DIV_5V
    print (voltage2)
    
    return voltage, voltage2



def DSUB2():
    channel = Channels_DSUB2[0]
    bus.write_byte(I2C_ADD, channel)   # send address byte for channel 
    time.sleep(0.02)
    output = bus.read_i2c_block_data(I2C_ADD, channel, 3) #read ouput raw data from 3 bytes
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6) #extract 16 bit value from 3 bytes
    voltage3 = float(Voltage_ref*raw_val/ADC_raw_factor)/DIV_12V #convert 16 bit to voltage against reference VCC voltage
    print (voltage3)
    channel = Channels_DSUB2[1]
    bus.write_byte(I2C_ADD, channel)   # send address byte for channel 
    output = bus.read_i2c_block_data(I2C_ADD, channel, 3) #read ouput raw data from 3 bytes
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6) #extract 16 bit value from 3 bytes
    voltage4 = float(Voltage_ref*raw_val/ADC_raw_factor)/DIV_5V #convert 16 bit to voltage against reference VCC voltage
    print (voltage4)
    
    return voltage3, voltage4
    

def DSUB3A():
    channel = Channels_DSUB3A[0]
    bus.write_byte(I2C_ADD, channel)   # send address byte for channel 
    time.sleep(0.02)
    output = bus.read_i2c_block_data(I2C_ADD, channel, 3) #read ouput raw data from 3 bytes
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6) #extract 16 bit value from 3 bytes
    voltage5 = float(Voltage_ref*raw_val/ADC_raw_factor)/DIV_12V #convert 16 bit to voltage against reference VCC votlage
    print (voltage5)
    channel = Channels_DSUB3A[1]
    bus.write_byte(I2C_ADD, channel)   # send address byte for channel 
    output = bus.read_i2c_block_data(I2C_ADD, channel, 3) #read ouput raw data from 3 bytes
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6) #extract 16 bit value from 3 bytes
    voltage6 = float(Voltage_ref*raw_val/ADC_raw_factor)/DIV_5V #convert 16 bit to voltage against reference VCC voltage
    print (voltage6)
    
    return voltage5, voltage6
    


def DSUB3B():     #IFV only
    channel = Channels_DSUB3B[0]
    bus.write_byte(I2C_ADD, channel)   # send address byte for channel 
    time.sleep(0.02)
    output = bus.read_i2c_block_data(I2C_ADD, channel, 3) #read ouput raw data from 3 bytes
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6) #extract 16 bit value from 3 bytes
    voltage7 = float(Voltage_ref*raw_val/ADC_raw_factor)/DIV_12V #convert 16 bit to voltage against reference VVC voltage
    print (voltage7)
    channel = Channels_DSUB3B[1]
    bus.write_byte(I2C_ADD, channel)   # send address byte for channel 
    output = bus.read_i2c_block_data(I2C_ADD, channel, 3) #read ouput raw data from 3 bytes
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6) #extract 16 bit value from 3 bytes
    voltage8 = float(Voltage_ref*raw_val/ADC_raw_factor)/DIV_5V #convert 16 bit to voltage against reference VCC voltage
    print (voltage8)
    
    return voltage7, voltage8
    

def DSUB_Power():
    channel = Channels_DSUB_Power[0]
    bus.write_byte(I2C_ADD, channel)   # send address byte for channel
    time.sleep(0.02) 
    output = bus.read_i2c_block_data(I2C_ADD, channel, 3) #read ouput raw data from 3 bytes
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6) #extract 16 bit value from 3 bytes
    voltage9= float(Voltage_ref*raw_val/ADC_raw_factor)/DIV_50V #convert 16 bit to voltage against reference VCC voltage
    print (voltage9)

    return voltage9



# Check if voltages are correct -- confirm wwhich voltage divider is fror which pin and if tolerance is enough //may need to adjust and say serial, SBUS instead of DSUB1 ect

voltage, voltage2 = DSUB1()
if (11.5 <= voltage <= 12.5) and (4.5 <= voltage2 <= 5.5):
    print("voltage DSUB1 Pass")
else:
    print("voltage DSUB1 Fail")

voltage3, voltage4 = DSUB2() #can/SBUS
if (11.5 <= voltage3 <= 12.5) and (4.5 <= voltage4 <= 5.5):
    print("voltage DSUB2 Pass")
else:
    print("voltage DSUB2 Fail")


voltage5, voltage6 = DSUB3A() #serial 
if (11.5 <= voltage5 <= 12.5) and (4.5 <= voltage6 <= 5.5):
    print("voltage DSUB3A Pass")
else:
    print("voltage DSUB3A Fail")

voltage7, voltage8 = DSUB3B()  #IFV only serial
if (11.5 <= voltage7 <= 12.5) and (4.5 <= voltage8 <= 5.5):
    print("voltage DSUB3B Pass")
else:
    print("voltage DSUB3B Fail")

voltage9 = DSUB_Power()
if (49.5 <= voltage9 <= 50.5):
    print("voltage DSUB Power Pass")
else:
    print("voltage DSUB Power Fail")

