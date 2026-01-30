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
    start_wait = time.time()
    # SBUS is inverted: Idle is 1, Start bit is 0
    while lgpio.gpio_read(h, SBUS_GPIO) == 1:
        if time.time() - start_wait > 0.1: return None
    
    time.sleep(1.5 * BIT_TIME_US / 1_000_000)
    value = 0
    for i in range(8):
        bit = lgpio.gpio_read(h, SBUS_GPIO)
        value |= (bit << i)
        time.sleep(BIT_TIME_US / 1_000_000)
    
    return value ^ 0xFF

def sync_sbus():
    # Wait for frame gap (idle time)
    idle_start = time.time()
    while time.time() - idle_start < 0.004:
        if lgpio.gpio_read(h, SBUS_GPIO) == 0:
            idle_start = time.time()

try:
    while True:
        sync_sbus() 
        frame = []
        for _ in range(SBUS_FRAME_LENGTH):
            b = read_sbus_byte()
            if b is not None: 
                frame.append(b)
        
        if len(frame) == SBUS_FRAME_LENGTH and frame[0] == SBUS_HEADER:
            print("SBUS Connected **PASS**")
        else:
            print("SBUS not detected **FAIL**")
            
except KeyboardInterrupt:
    pass
finally:
    lgpio.gpiochip_close(h)