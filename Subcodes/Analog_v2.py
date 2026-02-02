import time
import smbus2

I2C_ADD = 0x45
bus = smbus2.SMBus(1)

Voltage_ref = 3.3
ADC_raw_factor = 65535.0

DIV_12V = 0.2448
DIV_5V  = 0.5
DIV_50V = 0.032

CH_DSUB1 = [0xB8, 0xB1]
CH_DSUB2 = [0xB2, 0xBA]
CH_DSUB3A = [0xBB, 0xB4]
CH_DSUB3B = [0xB5, 0xBD]
CH_POWER  = 0xBE

def _decode_voltage(output, divider):
    # your original extraction (minimal change)
    raw_val = ((output[0] & 0x3F) << 10) | (output[1] << 2) | (output[2] >> 6)
    return (Voltage_ref * raw_val / ADC_raw_factor) / divider

def read_max_until_in_range(channel_cmd, divider, vmin, vmax, timeout=1.0, conv_wait=0.18):
    """
    Loop until voltage is within [vmin, vmax] OR timeout reached.
    Track and return the biggest successfully-read voltage during the timeout window.
    """
    t0 = time.time()
    vmax_seen = None

    while (time.time() - t0) < timeout:
        try:
            # Start next conversion
            bus.write_byte(I2C_ADD, channel_cmd)

            # Flush old result (LTC2497 can return previous conversion immediately)
            try:
                _ = bus.read_i2c_block_data(I2C_ADD, 0x00, 3)
            except OSError:
                pass  # ignore flush failures

            # Give conversion time (keeps behavior stable)
            time.sleep(conv_wait)

            # Read result
            output = bus.read_i2c_block_data(I2C_ADD, 0x00, 3)
            v = _decode_voltage(output, divider)

            # Track biggest value seen
            if vmax_seen is None or v > vmax_seen:
                vmax_seen = v

            # Exit early if we're in-range
            if vmin <= v <= vmax:
                break

        except OSError:
            # Treat as "no reading this time" — keep the max we already saw
            time.sleep(0.01)

    return round(vmax_seen, 2) if vmax_seen is not None else 0.0


# ---- Example usage: your channel groups & ranges ----

# 5V channels: (DSUB1-5V, DSUB2-5V, DSUB3A-5V, DSUB3B-5V)
v2 = read_max_until_in_range(CH_DSUB1[1], DIV_5V,  4.5,  5.5, timeout=1.0)
v4 = read_max_until_in_range(CH_DSUB2[1], DIV_5V,  4.5,  5.5, timeout=1.0)
v6 = read_max_until_in_range(CH_DSUB3A[1], DIV_5V, 4.5,  5.5, timeout=1.0)
v8 = read_max_until_in_range(CH_DSUB3B[1], DIV_5V, 4.5,  5.5, timeout=1.0)

# 12V channels: (DSUB1-12V, DSUB2-12V, DSUB3A-12V, DSUB3B-12V)
v1 = read_max_until_in_range(CH_DSUB1[0], DIV_12V, 11.5, 12.5, timeout=1.0)
v3 = read_max_until_in_range(CH_DSUB2[0], DIV_12V, 11.5, 12.5, timeout=1.0)
v5 = read_max_until_in_range(CH_DSUB3A[0], DIV_12V, 11.5, 12.5, timeout=1.0)
v7 = read_max_until_in_range(CH_DSUB3B[0], DIV_12V, 11.5, 12.5, timeout=1.0)

# 50V channel
v9 = read_max_until_in_range(CH_POWER, DIV_50V, 48.5, 52.0, timeout=1.0)

print("12V:", v1, v3, v5, v7)
print("5V :", v2, v4, v6, v8)
print("50V:", v9)