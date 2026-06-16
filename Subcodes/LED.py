import lgpio

LED_GPIO = 6
CHIP = 4
h = None

def INIT():
    global h
    try:
        if h is None:
            h = lgpio.gpiochip_open(CHIP)
            lgpio.gpio_claim_output(h, LED_GPIO)
            lgpio.gpio_write(h, LED_GPIO, 0)
            print("[LED] INIT -> LOW")
    except Exception as e:
        print("[LED] INIT ERROR:", e)

def LED_ON():
    try:
        INIT()
        lgpio.gpio_write(h, LED_GPIO, 1)
        print("[LED] ON")
    except Exception as e:
        print("[LED] ON ERROR:", e)

def LED_OFF():
    try:
        INIT()
        lgpio.gpio_write(h, LED_GPIO, 0)
        print("[LED] OFF")
    except Exception as e:
        print("[LED] OFF ERROR:", e)

def CLOSE():
    global h
    try:
        if h is not None:
            lgpio.gpio_write(h, LED_GPIO, 0)
            lgpio.gpiochip_close(h)
            print("[LED] CLOSE")
    except Exception as e:
        print("[LED] CLOSE ERROR:", e)
    finally:
        h = None