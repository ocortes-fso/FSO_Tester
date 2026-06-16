import time
import lgpio

PWM1 = 7
PWM2 = 5
CHIP = 4

INIT = 1140
HIGH = 1250
HIGHER = 1370
LOW = 1000
SWEEP_DELAY = 0.005


def set_pwm(h, us, target_pins):
    print(f"PWM {us}")
    for pin in target_pins:
        lgpio.tx_servo(h, pin, us)


def manual_sweep(h, start_us, end_us, target_pins, custom_delay=SWEEP_DELAY):
    step = 1 if end_us > start_us else -1
    for us in range(start_us, end_us + step, step):
        set_pwm(h, us, target_pins)
        time.sleep(custom_delay)

#call for normal spin test NO PROPS!!

def SPIN_START():
    global h
    try:
        pins = [PWM1, PWM2]

        manual_sweep(h, LOW, INIT, pins)
        time.sleep(1.0)

        manual_sweep(h, INIT, HIGH, pins)
        time.sleep(5.0)

        manual_sweep(h, HIGH, LOW, pins)

    except Exception as e:
        print(f"EXCEPTION: {e}")
        raise
    finally:
        if h is not None:
            lgpio.tx_servo(h, PWM1, 0)
            lgpio.tx_servo(h, PWM2, 0)


#call for Spin test PWM1 / TOP

def SPIN_TOP():
    global h
    try:
        pins = [PWM1]

        manual_sweep(h, LOW, INIT, pins)
        time.sleep(1.0)

        manual_sweep(h, INIT, HIGH, pins)
        time.sleep(5.0)

        manual_sweep(h, HIGH, LOW, pins)

    except Exception as e:
        print(f"EXCEPTION: {e}")
        raise
    finally:
        if h is not None:
            lgpio.tx_servo(h, PWM1, 0)


#call for Spin test PWM2 / BOT

def SPIN_BOT():
    global h
    try:
        pins = [PWM2]

        manual_sweep(h, LOW, INIT, pins)
        time.sleep(1.0)

        manual_sweep(h, INIT, HIGH, pins)
        time.sleep(5.0)

        manual_sweep(h, HIGH, LOW, pins)

    except Exception as e:
        print(f"EXCEPTION: {e}")
        raise
    finally:
        if h is not None:
            lgpio.tx_servo(h, PWM2, 0)


#call for vibration/prop spin test WITH PROPS!!
    #adjust delays if needed for ramp up
    # 1350-1140 = 210, 210x0.2 = 42 seconds

    #expected bahviour.. go to INIT, hold, ramp up to higher with slower ramp speed than other tests, hold, perform 3 pulses, ramp down at sweep speed


def SPIN_PROP():
    global h
    try:
        pins = [PWM1, PWM2]

        manual_sweep(h, LOW, INIT, pins)
        time.sleep(1.0)

        manual_sweep(h, INIT, HIGHER, pins, custom_delay=0.2)

        time.sleep(30.0)

        PULSE_MAX = HIGHER + 30
        for _ in range(3):
            manual_sweep(h, HIGHER, PULSE_MAX, pins, custom_delay=0.02)
            time.sleep(3.0)
            manual_sweep(h, PULSE_MAX, HIGHER, pins, custom_delay=0.02)
            time.sleep(5.0)

        manual_sweep(h, HIGHER, LOW, pins)

    except Exception as e:
        print(f"EXCEPTION: {e}")
        raise
    finally:
        if h is not None:
            lgpio.tx_servo(h, PWM1, 0)
            lgpio.tx_servo(h, PWM2, 0)