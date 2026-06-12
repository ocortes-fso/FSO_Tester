#PWM to control DIMM to LED driver, 3.3V logic high = 1, low = 0 

import time
import lgpio

LED_GPIO = 6
CHIP = 4

#main logic 

def LED_ON():
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, LED_GPIO)


        def turn_on_led():

            lgpio.gpio_write(h, LED_GPIO, 1)

        def turn_off_led():
            lgpio.gpio_write(h, LED_GPIO, 0)

    except Exception as e:
        pass


    finally:
        if 'h' in locals():
            lgpio.gpio_write(h, LED_GPIO, 0)
            lgpio.gpiochip_close(h)
    