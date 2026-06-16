import time
import lgpio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import Precharge

PWM1 = 7
PWM2 = 5

INIT = 1100
HIGH = 1250
HIGHER = 1370
LOW = 1000
SWEEP_DELAY = 0.05


def set_pwm(us, target_pins):
    for pin in target_pins:
        try:
            lgpio.tx_servo(Precharge.h, pin, us)
            print(f"PWM OK: pin={pin} us={us}")
        except Exception as e:
            print(f"PWM ERROR: pin={pin} us={us} err={e}")


def manual_sweep(start_us, end_us, target_pins, custom_delay=SWEEP_DELAY, step_size=10):
    if start_us == end_us:
        set_pwm(end_us, target_pins)
        return

    step = step_size if end_us > start_us else -step_size
    current_us = start_us

    while True:
        set_pwm(current_us, target_pins)
        
        actual_delay = max(custom_delay, 0.02)
        time.sleep(actual_delay)
        
        if (step > 0 and current_us + step >= end_us) or (step < 0 and current_us + step <= end_us):
            break
        current_us += step

    set_pwm(end_us, target_pins)


def SPIN_START():
    try:
        if Precharge.h is None:
            print("SPIN_START ERROR: GPIO handle is None")
            return

        pins = [PWM1, PWM2]

        set_pwm(LOW, pins)
        time.sleep(1.0)

        manual_sweep(LOW, INIT, pins, custom_delay=0.05, step_size=10)
        time.sleep(3.0)

        manual_sweep(INIT, HIGH, pins, custom_delay=0.05, step_size=10)
        time.sleep(5.0)

        manual_sweep(HIGH, LOW, pins, custom_delay=0.05, step_size=10)

    except Exception as e:
        print(f"SPIN_START EXCEPTION: {e}")
        raise

    finally:
        if Precharge.h is not None:
            try:
                lgpio.tx_servo(Precharge.h, PWM1, 0)
                lgpio.tx_servo(Precharge.h, PWM2, 0)
            except Exception as e:
                print(f"PWM STOP ERROR: {e}")


def SPIN_TOP():
    try:
        if Precharge.h is None:
            print("SPIN_TOP ERROR: GPIO handle is None")
            return

        pins = [PWM1]

        set_pwm(LOW, pins)
        time.sleep(1.0)

        manual_sweep(LOW, INIT, pins, custom_delay=0.05, step_size=10)
        time.sleep(3.0)

        manual_sweep(INIT, HIGH, pins, custom_delay=0.05, step_size=10)
        time.sleep(5.0)

        manual_sweep(HIGH, LOW, pins, custom_delay=0.05, step_size=10)

    except Exception as e:
        print(f"SPIN_TOP EXCEPTION: {e}")
        raise

    finally:
        if Precharge.h is not None:
            try:
                lgpio.tx_servo(Precharge.h, PWM1, 0)
            except Exception as e:
                print(f"PWM STOP ERROR: {e}")


def SPIN_BOT():
    try:
        if Precharge.h is None:
            print("SPIN_BOT ERROR: GPIO handle is None")
            return

        pins = [PWM2]

        set_pwm(LOW, pins)
        time.sleep(1.0)

        manual_sweep(LOW, INIT, pins, custom_delay=0.05, step_size=10)
        time.sleep(3.0)

        manual_sweep(INIT, HIGH, pins, custom_delay=0.05, step_size=10)
        time.sleep(5.0)

        manual_sweep(HIGH, LOW, pins, custom_delay=0.05, step_size=10)

    except Exception as e:
        print(f"SPIN_BOT EXCEPTION: {e}")
        raise

    finally:
        if Precharge.h is not None:
            try:
                lgpio.tx_servo(Precharge.h, PWM2, 0)
            except Exception as e:
                print(f"PWM STOP ERROR: {e}")


def SPIN_PROP():
    try:
        if Precharge.h is None:
            print("SPIN_PROP ERROR: GPIO handle is None")
            return

        pins = [PWM1, PWM2]

        set_pwm(LOW, pins)
        time.sleep(1.0)

        manual_sweep(LOW, INIT, pins, custom_delay=0.05, step_size=10)
        time.sleep(3.0)

        manual_sweep(INIT, HIGHER, pins, custom_delay=0.05, step_size=10)

        time.sleep(30.0)

        PULSE_MAX = HIGHER + 30

        for _ in range(3):
            manual_sweep(HIGHER, PULSE_MAX, pins, custom_delay=0.02, step_size=5)
            time.sleep(3.0)

            manual_sweep(PULSE_MAX, HIGHER, pins, custom_delay=0.02, step_size=5)
            time.sleep(5.0)

        manual_sweep(HIGHER, LOW, pins, custom_delay=0.05, step_size=10)

    except Exception as e:
        print(f"SPIN_PROP EXCEPTION: {e}")
        raise

    finally:
        if Precharge.h is not None:
            try:
                lgpio.tx_servo(Precharge.h, PWM1, 0)
                lgpio.tx_servo(Precharge.h, PWM2, 0)
            except Exception as e:
                print(f"PWM STOP ERROR: {e}")