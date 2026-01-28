import time 
import smbus2 

# --- Configuration ---
I2C_ADD = 0x45  
bus = smbus2.SMBus(1)
Voltage_ref = 3.3
ADC_raw_factor = 65535.0

# Voltage Dividers (Rbot / (Rbot + Rtop))
DIV_12V = 0.2448
DIV_5V = 0.5
DIV_50V = 0.032

# Channels (LTC2497 Hex Commands)
CH_DSUB1 = [0xB8, 0xB1]
CH_DSUB2 = [0xB2, 0xBA]
CH_DSUB3A = [0xBB, 0xB4]
CH_DSUB3B = [0xB5, 0xBD]
CH_POWER  = 0xBE

def read_adc_safe(channel, divider, label):
 
    try:
        # Step 1: Tell ADC which channel to read next
        bus.write_byte(I2C_ADD, channel)
        time.sleep(0.03) # Slightly longer sleep for stability
        
        # Step 2: Read the 3 bytes from the conversion
        output = bus.read_i2c_block_data(I2C_ADD, channel, 3)
        
        # Step 3: Extract 16-bit value from the 24-bit LTC output
        # (Assuming standard LTC2497 3-byte format)
        raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6)
        
        voltage = (Voltage_ref * raw_val / ADC_raw_factor) / divider
        return round(voltage, 2)
    
    except OSError:
        # This triggers if the I2C bus doesn't see the device (wire unplugged)
        print(f"  [!] {label} Communication Error: Pin/Wire not detected.")
        return 0.0

# --- DSUB 1 ---
v1 = read_adc_safe(CH_DSUB1[0], DIV_12V, "DSUB1-12V")
v2 = read_adc_safe(CH_DSUB1[1], DIV_5V, "DSUB1-5V")
res1 = "PASS" if (11.5 <= v1 <= 12.5 and 4.5 <= v2 <= 5.5) else "FAIL"
print(f"DSUB 1 Results: {v1}V, {v2}V -> {res1}")

# --- DSUB 2 ---
v3 = read_adc_safe(CH_DSUB2[0], DIV_12V, "DSUB2-12V")
v4 = read_adc_safe(CH_DSUB2[1], DIV_5V, "DSUB2-5V")
res2 = "PASS" if (11.5 <= v3 <= 12.5 and 4.5 <= v4 <= 5.5) else "FAIL"
print(f"DSUB 2 Results: {v3}V, {v4}V -> {res2}")

# --- DSUB 3A ---
v5 = read_adc_safe(CH_DSUB3A[0], DIV_12V, "DSUB3A-12V")
v6 = read_adc_safe(CH_DSUB3A[1], DIV_5V, "DSUB3A-5V")
res3 = "PASS" if (11.5 <= v5 <= 12.5 and 4.5 <= v6 <= 5.5) else "FAIL"
print(f"DSUB 3A Results: {v5}V, {v6}V -> {res3}")

# --- DSUB 3B ---
v7 = read_adc_safe(CH_DSUB3B[0], DIV_12V, "DSUB3B-12V")
v8 = read_adc_safe(CH_DSUB3B[1], DIV_5V, "DSUB3B-5V")
res4 = "PASS" if (11.5 <= v7 <= 12.5 and 4.5 <= v8 <= 5.5) else "FAIL"
print(f"DSUB 3B Results: {v7}V, {v8}V -> {res4}")

# --- DSUB Power ---
v9 = read_adc_safe(CH_POWER, DIV_50V, "POWER-50V")
res5 = "PASS" if (49.5 <= v9 <= 50.5) else "FAIL"
print(f"DSUB Power Result: {v9}V -> {res5}")
