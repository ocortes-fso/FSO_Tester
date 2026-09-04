import lgpio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import Precharge

LED_GPIO = 6

def INIT():
    try:
        h = Precharge.h

        if h is None:
            print("[LED] INIT ERROR: Precharge not initialized")
            return

        lgpio.gpio_claim_output(h, LED_GPIO, 0)
        print("[LED] INIT -> LOW")

    except Exception as e:
        print("[LED] INIT ERROR:", e)



def LED_ON():
    try:
        h = Precharge.h
        if h is None:
            print("[LED] ERROR: Precharge not initialized")
            return
        lgpio.gpio_write(h, LED_GPIO, 1)
        print("[LED] ON")

    except Exception as e:
        print("[LED] ON ERROR:", e)


def LED_OFF():
    try:
        h = Precharge.h
        if h is None:
            print("[LED] ERROR: Precharge not initialized")
            return
        lgpio.gpio_write(h, LED_GPIO, 0)
        print("[LED] OFF")

    except Exception as e:
        print("[LED] OFF ERROR:", e)