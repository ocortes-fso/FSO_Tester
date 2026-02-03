import time
import smbus2

I2C_ADD = 0x45
bus = smbus2.SMBus(1)

Voltage_ref = 3.3
ADC_raw_factor = 65535.0

# Voltage Dividers (Rbot / (Rbot + Rtop))
DIV_12V = 0.1393786733837112
DIV_5V  = 0.3329989969909729
DIV_50V = 0.0328973444312327

# Ghost detection thresholds
GHOST_12V = 23.68   # ~ 2 * 11.84
GHOST_5V = 9.91     # ~ 2 * 4.95
GHOST_50V = 100.31  # ~ 2 * 50.16

GHOST_12V_TOL = 1.0 
GHOST_5V_TOL = 0.5 
GHOST_50V_TOL = 1.5

# Channel ADDRS
CH_DSUB1 = [0xB8, 0xB1]
CH_DSUB2 = [0xB2, 0xBA]
CH_DSUB3A = [0xBB, 0xB4]
CH_DSUB3B = [0xB5, 0xBD]
CH_POWER  = 0xBE

def _decode_voltage(output, divider):
    # your original extraction (minimal change)
    raw_val = ((output[0] & 0x7F) << 16) | (output[1] << 8) | output[2]
    return (Voltage_ref * raw_val / (1 << 23)) / divider

def suppress_floating(voltage, vmin, vmax, channel_type):
    # Valid in-range value → keep it
    if vmin <= voltage <= vmax:
        return voltage

    # Ghost patterns → force to 0V
    if channel_type == "12V":
        if abs(voltage - GHOST_12V) < GHOST_12V_TOL:
            return 0.0

    elif channel_type == "5V":
        if abs(voltage - GHOST_5V) < GHOST_5V_TOL:
            return 0.0

    elif channel_type == "50V":
        if abs(voltage - GHOST_50V) < GHOST_50V_TOL:
            return 0.0

    return voltage

def read_max_until_in_range(channel_cmd, divider, vmin, vmax, channel_type, label, timeout=1.0, conv_wait=0.18):
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
            v = suppress_floating(v, vmin, vmax, channel_type)

            # Track biggest value seen
            if vmax_seen is None or v > vmax_seen:
                vmax_seen = v

            # Exit early if we're in-range
            if vmin <= v <= vmax:
                break

        except OSError:
            # Treat as "no reading this time" — keep the max we already saw
            time.sleep(0.01)

    value = round(vmax_seen, 2) if vmax_seen is not None else 0.0
    in_range = (vmin <= value <= vmax)

    return {
        "label": label,
        "value": value,
        "pass": in_range,
        "in_range": in_range
    }

##### Read all Voltages #####
def read_all_channels(timeout=1.0, conv_wait=0.18):
    results = []

    # DSUB1
    results.append(read_max_until_in_range(CH_DSUB1[0], DIV_12V, 11.5, 12.5, "12V", "CAN/SBUS-12V", timeout, conv_wait))
    results.append(read_max_until_in_range(CH_DSUB1[1], DIV_5V,  4.5,  5.5,  "5V",  "CAN/SBUS-5V", timeout, conv_wait))

    # DSUB2
    results.append(read_max_until_in_range(CH_DSUB2[0], DIV_12V, 11.5, 12.5, "12V", "RC OUT-12V", timeout, conv_wait))
    results.append(read_max_until_in_range(CH_DSUB2[1], DIV_5V,  4.5,  5.5,  "5V",  "RC OUT-5V", timeout, conv_wait))

    # DSUB3A
    results.append(read_max_until_in_range(CH_DSUB3A[0], DIV_12V, 11.5, 12.5, "12V", "STD SERIAL-12V", timeout, conv_wait))
    results.append(read_max_until_in_range(CH_DSUB3A[1], DIV_5V,  4.5,  5.5,  "5V",  "STD SERIAL-5V", timeout, conv_wait))

    # DSUB3B
    results.append(read_max_until_in_range(CH_DSUB3B[0], DIV_12V, 11.5, 12.5, "12V", "IV SERIAL-12V", timeout, conv_wait))
    results.append(read_max_until_in_range(CH_DSUB3B[1], DIV_5V,  4.5,  5.5,  "5V",  "IV SERIAL-5V", timeout, conv_wait))

    # Power
    results.append(read_max_until_in_range(CH_POWER, DIV_50V, 48.5, 52.0, "50V", "PAYLOAD", timeout, conv_wait))

    return results

##### Print #####
# for r in results:
#     status = "PASS" if r["pass"] else "FAIL"
#     print(f'{r["label"]}: {r["value"]} V -> {status}')
