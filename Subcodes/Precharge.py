import lgpio

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


def OPEN_FET():
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
            raise RuntimeError("GPIO chip not initialized")

        lgpio.gpio_write(h, PRECHARGE, 0)

    except Exception as e:
        print(f"PRECHARGE OFF ERROR: {e}")
        raise


def CLOSE_FET():
    global h
    try:
        if h is not None:
            lgpio.gpio_write(h, FET_CTL, 0)

    except Exception as e:
        print(f"FET CLOSE ERROR: {e}")

    finally:
        try:
            if h is not None:
                lgpio.gpiochip_close(h)
                h = None
        except Exception as e:
            print(f"GPIO CLOSE ERROR: {e}")
            h = None