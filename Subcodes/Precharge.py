import lgpio

FET_CTL = 0
PRECHARGE = 12
CHIP = 4

h = None


def INITIALIZE_SYSTEM():
    global h

    try:
        if h is None:
            h = lgpio.gpiochip_open(CHIP)

        try:
            lgpio.gpio_claim_output(h, PRECHARGE)
        except:
            pass

        try:
            lgpio.gpio_claim_output(h, FET_CTL)
        except:
            pass

        lgpio.gpio_write(h, FET_CTL, 0)
        lgpio.gpio_write(h, PRECHARGE, 1)

        print("System initialized and precharge off, FET off")

    except Exception as e:
        print(f"PRECHARGE INIT ERROR: {e}")
        raise


def START_PRECHARGE():
    global h

    try:
        if h is None:
            raise RuntimeError("GPIO chip not initialized")

        lgpio.gpio_write(h, PRECHARGE, 0)
        print("Precharge on")

    except Exception as e:
        print(f"PRECHARGE START ERROR: {e}")
        raise


def OPEN_FET():
    global h

    try:
        if h is None:
            raise RuntimeError("GPIO chip not initialized")

        lgpio.gpio_write(h, FET_CTL, 1)
        print("FET ON")

    except Exception as e:
        print(f"FET OPEN ERROR: {e}")
        raise


def TURN_OFF_PRECHARGE():
    global h

    try:
        if h is None:
            raise RuntimeError("GPIO chip not initialized")

        lgpio.gpio_write(h, PRECHARGE, 1)
        print("Precharge off")

    except Exception as e:
        print(f"PRECHARGE OFF ERROR: {e}")
        raise


def CLOSE_FET():
    global h

    if h is None:
        return

    try:
        lgpio.gpio_write(h, FET_CTL, 0)
        print("FET OFF")

    except Exception as e:
        print(f"FET CLOSE ERROR: {e}")

def CLOSE_SYSTEM():
    global h

    if h is None:
        return

    try:
        lgpio.gpio_write(h, PRECHARGE, 1)
        lgpio.gpio_write(h, FET_CTL, 0)

        lgpio.gpiochip_close(h)

        print("GPIO CLOSED and Precharge off, FET off")

    except Exception as e:
        print(f"GPIO CLOSE ERROR: {e}")

    finally:
        h = None