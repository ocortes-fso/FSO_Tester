import lgpio
import time

FET_CTL = 0
PRECHARGE = 12
CHIP = 4

h = None

def INITIALIZE_SYSTEM():
    global h
    try:
        if h is None:
            h = lgpio.gpiochip_open(CHIP)
            lgpio.gpio_claim_output(h, PRECHARGE, level=0)
            lgpio.gpio_claim_output(h, FET_CTL, level=0)
            time.sleep(0.1)
            print("Precharge Pins successfully claimed LOW.")
    except Exception as e:
        print(f"PRECHARGE INIT ERROR: {e}")
        raise

def START_PRECHARGE():
    global h
    try:
        if h is None:
            raise RuntimeError("GPIO chip not initialized")
        lgpio.gpio_write(h, PRECHARGE, 1)
    except Exception as e:
        print(f"PRECHARGE START ERROR: {e}")
        raise

def TURN_ON_MAIN_FET():
    global h
    try:
        if h is None:
            raise RuntimeError("GPIO chip not initialized")
        lgpio.gpio_write(h, FET_CTL, 1)
    except Exception as e:
        print(f"FET OPEN ERROR: {e}")
        raise

def TURN_OFF_PRECHARGE():
    global h
    try:
        if h is None:
            INITIALIZE_SYSTEM()

        lgpio.gpio_write(h, PRECHARGE, 0)

    except Exception as e:
        print(f"PRECHARGE OFF ERROR: {e}")
        raise

def CLOSE_FET():
    global h
    try:
        if h is None:
            INITIALIZE_SYSTEM()

        lgpio.gpio_write(h, FET_CTL, 0)

        print("MAIN FET OFF")

    except Exception as e:
        print(f"FET CLOSE ERROR: {e}")
        raise

def SAFETY_SHUTDOWN_FAULT():
    global h
    try:
        if h is not None:
            lgpio.gpio_write(h, PRECHARGE, 0)
            lgpio.gpio_write(h, FET_CTL, 0)
            lgpio.gpiochip_close(h)
            h = None
    except Exception as e:
        print(f"GPIO CLOSE ERROR: {e}")
        h = None