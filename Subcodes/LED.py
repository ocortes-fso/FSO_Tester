#PWM to control DIMM to LED driver, 3.3V logic high = 1, low = 0 

import time
import lgpio

LED_GPIO = 6
CHIP = 4

#main logic 


#chip left open since remains high, then closed when hitting off button.. work into GUI 

def LED_ON():
    global h
    try:
        lgpio.gpio_claim_output(h, LED_GPIO)
        lgpio.gpio_write(h, LED_GPIO, 1)
    except Exception as e:
        pass


def LED_OFF():
    global h
    try:
        lgpio.gpio_claim_output(h, LED_GPIO)
        lgpio.gpio_write(h, LED_GPIO, 0)
        
    except Exception as e:
        pass
