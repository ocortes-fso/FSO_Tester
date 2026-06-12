#coinditions for the mosfet turning on to be handled in the GUI using the batteyr monitor data. Precharge happens first and the mosfet turns on. Need to consider naming for button in GUI maybe just call POWER ON ect..
#Close of global h by calling close fet should be last thing done. which will be the case as LED driver also needs that on to work.

import lgpio
import time

FET_CTL = 0
PRECHARGE = 12
CHIP = 4

h = None


def INITIALIZE_SYSTEM():
    global h
    try:
        h = lgpio.gpiochip_open(CHIP)
        lgpio.gpio_claim_output(h, PRECHARGE)
        lgpio.gpio_claim_output(h, FET_CTL)
    except Exception as e:
        pass


def START_PRECHARGE():
    try:
        lgpio.gpio_write(h, PRECHARGE, 1)
    except Exception as e:
        pass


def OPEN_FET():
    try:
        lgpio.gpio_write(h, FET_CTL, 1)
    except Exception as e:
        pass


def TURN_OFF_PRECHARGE():
    try:
        lgpio.gpio_write(h, PRECHARGE, 0)
    except Exception as e:
        pass


def CLOSE_FET():
    global h
    try:
        lgpio.gpio_write(h, FET_CTL, 0)
    except Exception as e:
        pass
    finally:
        if h is not None:
            try:
                lgpio.gpiochip_close(h)
                h = None
            except Exception:
                pass