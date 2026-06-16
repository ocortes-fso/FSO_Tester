import time
import lgpio
import os
import sys
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import Precharge

DRIVE_12MA = 12 << 4
SLEW_FAST = 1 << 8

PWM1 = 7
PWM2 = 5

INIT = 1100
HIGH = 1250
HIGHER = 1360
LOW = 1000
SWEEP_DELAY = 0.05


def claim_pwm_pins():
    try:
        lgpio.gpio_claim_output(Precharge.h, PWM1, level=0)
        print(f"CLAIM OK GPIO{PWM1}")
    except Exception as e:
        print(f"CLAIM FAIL GPIO{PWM1}: {e}")

    try:
        lgpio.gpio_claim_output(Precharge.h, PWM2, level=0)
        print(f"CLAIM OK GPIO{PWM2}")
    except Exception as e:
        print(f"CLAIM FAIL GPIO{PWM2}: {e}")


def set_pwm(us, target_pins):
    for pin in target_pins:
        try:
            ret = lgpio.tx_servo(Precharge.h, pin, us)
            print(
                f"PWM OK thread={threading.get_ident()} "
                f"handle={Precharge.h} pin={pin} us={us} ret={ret}"
            )
        except Exception as e:
            print(
                f"PWM ERROR thread={threading.get_ident()} "
                f"handle={Precharge.h} pin={pin} us={us} err={e}"
            )


def manual_sweep(start_us, end_us, target_pins, custom_delay=SWEEP_DELAY, step_size=2):
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
        print(f"SPIN_START BEGIN thread={threading.get_ident()} handle={Precharge.h}")

        if Precharge.h is None:
            print("SPIN_START ERROR: GPIO handle is None")
            return

        claim_pwm_pins()

        pins = [PWM1, PWM2]

        set_pwm(LOW, pins)
        time.sleep(0.5)

        manual_sweep(LOW, INIT, pins, custom_delay=0.05, step_size=10)
        time.sleep(1.5)

        manual_sweep(INIT, HIGH, pins, custom_delay=0.05, step_size=10)
        time.sleep(10.0)

        manual_sweep(HIGH, LOW, pins, custom_delay=0.05, step_size=10)

        print("SPIN_START COMPLETE")

    except Exception as e:
        print(f"SPIN_START EXCEPTION: {e}")
        raise

    finally:
        if Precharge.h is not None:
            try:
                print("STOP PWM1")
                ret1 = lgpio.tx_servo(Precharge.h, PWM1, 0)
                print(f"STOP GPIO{PWM1} ret={ret1}")

                print("STOP PWM2")
                ret2 = lgpio.tx_servo(Precharge.h, PWM2, 0)
                print(f"STOP GPIO{PWM2} ret={ret2}")

            except Exception as e:
                print(f"PWM STOP ERROR: {e}")


def SPIN_TOP():
    try:
        print(f"SPIN_TOP BEGIN thread={threading.get_ident()} handle={Precharge.h}")

        if Precharge.h is None:
            print("SPIN_TOP ERROR: GPIO handle is None")
            return

        claim_pwm_pins()

        pins = [PWM1]

        set_pwm(LOW, pins)
        time.sleep(0.5)

        manual_sweep(LOW, INIT, pins, custom_delay=0.05, step_size=10)
        time.sleep(1.5)

        manual_sweep(INIT, HIGH, pins, custom_delay=0.05, step_size=10)
        time.sleep(5.0)

        manual_sweep(HIGH, LOW, pins, custom_delay=0.05, step_size=10)

        print("SPIN_TOP COMPLETE")

    except Exception as e:
        print(f"SPIN_TOP EXCEPTION: {e}")
        raise

    finally:
        if Precharge.h is not None:
            try:
                print("STOP PWM1")
                ret = lgpio.tx_servo(Precharge.h, PWM1, 0)
                print(f"STOP GPIO{PWM1} ret={ret}")

            except Exception as e:
                print(f"PWM STOP ERROR: {e}")


def SPIN_BOT():
    try:
        print(f"SPIN_BOT BEGIN thread={threading.get_ident()} handle={Precharge.h}")

        if Precharge.h is None:
            print("SPIN_BOT ERROR: GPIO handle is None")
            return

        claim_pwm_pins()

        pins = [PWM2]

        set_pwm(LOW, pins)
        time.sleep(0.5)

        manual_sweep(LOW, INIT, pins, custom_delay=0.05, step_size=10)
        time.sleep(1.5)

        manual_sweep(INIT, HIGH, pins, custom_delay=0.05, step_size=10)
        time.sleep(5.0)

        manual_sweep(HIGH, LOW, pins, custom_delay=0.05, step_size=10)

        print("SPIN_BOT COMPLETE")

    except Exception as e:
        print(f"SPIN_BOT EXCEPTION: {e}")
        raise

    finally:
        if Precharge.h is not None:
            try:
                print("STOP PWM2")
                ret = lgpio.tx_servo(Precharge.h, PWM2, 0)
                print(f"STOP GPIO{PWM2} ret={ret}")

            except Exception as e:
                print(f"PWM STOP ERROR: {e}")


def SPIN_PROP():
    try:
        print(f"SPIN_PROP BEGIN thread={threading.get_ident()} handle={Precharge.h}")

        if Precharge.h is None:
            print("SPIN_PROP ERROR: GPIO handle is None")
            return

        claim_pwm_pins()

        pins = [PWM1, PWM2]

        set_pwm(LOW, pins)
        time.sleep(0.5)

        manual_sweep(LOW, INIT, pins, custom_delay=0.05, step_size=10)
        time.sleep(1.5)

        manual_sweep(INIT, HIGHER, pins, custom_delay=0.05, step_size=10)

        time.sleep(30.0)

        PULSE_MAX = HIGHER + 30

        for _ in range(3):
            manual_sweep(HIGHER, PULSE_MAX, pins, custom_delay=0.02, step_size=5)
            time.sleep(3.0)

            manual_sweep(PULSE_MAX, HIGHER, pins, custom_delay=0.02, step_size=5)
            time.sleep(5.0)

        manual_sweep(HIGHER, LOW, pins, custom_delay=0.05, step_size=10)

        print("SPIN_PROP COMPLETE")

    except Exception as e:
        print(f"SPIN_PROP EXCEPTION: {e}")
        raise

    finally:
        if Precharge.h is not None:
            try:
                print("STOP PWM1")
                ret1 = lgpio.tx_servo(Precharge.h, PWM1, 0)
                print(f"STOP GPIO{PWM1} ret={ret1}")

                print("STOP PWM2")
                ret2 = lgpio.tx_servo(Precharge.h, PWM2, 0)
                print(f"STOP GPIO{PWM2} ret={ret2}")

            except Exception as e:
                print(f"PWM STOP ERROR: {e}")