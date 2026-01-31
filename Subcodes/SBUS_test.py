import time
import lgpio

def test_sbus():
    SBUS_GPIO = 15
    SBUS_CHIP = 4
    BIT_TIME_US = 10
    SBUS_FRAME_LENGTH = 25
    SBUS_HEADER = 0x0F

    h = lgpio.gpiochip_open(SBUS_CHIP)
    lgpio.gpio_claim_input(h, SBUS_GPIO)

    def read_sbus_byte():
        # Wait for the next transition to LOW (Start bit)
        t_wait = time.time()
        while lgpio.gpio_read(h, SBUS_GPIO) == 1:
            if time.time() - t_wait > 0.5: # Prevent infinite hang if no signal
                return None
        
        # Jump to middle of first data bit
        time.sleep(1.5 * BIT_TIME_US / 1_000_000)
        
        value = 0
        for i in range(8):
            bit = lgpio.gpio_read(h, SBUS_GPIO)
            value |= (bit << i)
            time.sleep(BIT_TIME_US / 1_000_000)
        
        return value ^ 0xFF

    _sbus_read = False
    t0 = time.time()
    
    while time.time() - t0 < 5:  # Wait up to 5s for a valid header
        byte = read_sbus_byte()
        if byte == SBUS_HEADER:
            _sbus_read = True
            break # Exit loop early on success
        else:
            # If we see other data, just keep scanning silently
            pass
        
    lgpio.gpiochip_close(h)
    return _sbus_read