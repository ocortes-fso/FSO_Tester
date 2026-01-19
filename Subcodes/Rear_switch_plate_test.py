import time
import lgpio

RED_PIN = 0
GREEN_PIN = 1
BLUE_PIN = 7
SWITCH_PIN = 25
LED_SWITCH_PIN = 24

h = lgpio.gpiochip_open(4)

for pin in [RED_PIN, GREEN_PIN, BLUE_PIN, LED_SWITCH_PIN]:
    lgpio.gpio_claim_output(h, pin)

lgpio.gpio_claim_input(h, SWITCH_PIN, lgpio.SET_PULL_UP)

def set_rgb_colour(r, g, b):
    lgpio.gpio_write(h, RED_PIN, r)
    lgpio.gpio_write(h, GREEN_PIN, g)
    lgpio.gpio_write(h, BLUE_PIN, b)

rgb_values = [(1,0,0), (0,1,0), (0,0,1)] #high on 1 others low for r, g, b

try:
    while True:
        #Switch off - power button LED off, expected behaviour tatus LED cycles RGB and no switch red light
        if lgpio.gpio_read(h, SWITCH_PIN) == 0:
            lgpio.gpio_write(h, LED_SWITCH_PIN, 0)
            for colour in rgb_values:
                set_rgb_colour(*colour)
                time.sleep(0.4)
            
        #Switch on - power button LED on, status LED blinks RED fast
        elif lgpio.gpio_read(h, SWITCH_PIN) == 1:
             lgpio.gpio_write(h, LED_SWITCH_PIN, 1)
             while lgpio.gpio_read(h, SWITCH_PIN) == 1:
                set_rgb_colour(0, 0, 0)
                time.sleep(1)
                set_rgb_colour(1, 0, 0)
                time.sleep(1) 

except KeyboardInterrupt:
    pass
finally:
    lgpio.gpiochip_close(h)



import time, lgpio

SWITCH_PIN = 25

h = lgpio.gpiochip_open(4)
lgpio.gpio_claim_input(h, SWITCH_PIN, lgpio.SET_PULL_UP)

try:
    last = None
    while True:
        v = lgpio.gpio_read(h, SWITCH_PIN)
        if v != last:
            print("GPIO25 =", v)   # expect: 1 released, 0 pressed
            last = v
        time.sleep(0.01)
finally:
    lgpio.gpiochip_close(h)
