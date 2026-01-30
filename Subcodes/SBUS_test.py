import time
import lgpio

SBUS_GPIO = 15
SBUS_CHIP = 4
BIT_TIME_US = 10
SBUS_FRAME_LENGTH = 25
SBUS_HEADER = 0x0F

h = lgpio.gpiochip_open(SBUS_CHIP)
lgpio.gpio_claim_input(h, SBUS_GPIO)

def read_sbus_byte():
    # Wait for the next transition to LOW (Start bit)
    while lgpio.gpio_read(h, SBUS_GPIO) == 1:
        pass
    
    # Jump to middle of first data bit
    time.sleep(1.5 * BIT_TIME_US / 1_000_000)
    
    value = 0
    for i in range(8):
        bit = lgpio.gpio_read(h, SBUS_GPIO)
        value |= (bit << i)
        time.sleep(BIT_TIME_US / 1_000_000)
    
    return value ^ 0xFF

try:
    print("Scanning active SBUS stream...")
    while True:
        # Just grab one byte at a time and see if it's the header
        byte = read_sbus_byte()
        
        if byte == SBUS_HEADER:
            print("SBUS Connected **PASS**")
            # After a PASS, wait a moment so we don't spam the screen
            time.sleep(0.5)
        else:
            # If we see other data, just keep scanning silently
            pass
            
except KeyboardInterrupt:
    pass
finally:
    lgpio.gpiochip_close(h)