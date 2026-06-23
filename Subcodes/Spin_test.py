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
HIGH = 1280
HIGHER = 1400
LOW = 1000
SWEEP_DELAY = 0.05

_last_sent = {}

def claim_pwm_pins():
    try:
        lgpio.gpio_claim_output(Precharge.h, PWM1, level=0)
    except:
        pass

    try:
        lgpio.gpio_claim_output(Precharge.h, PWM2, level=0)
    except:
        pass

def set_pwm(us, target_pins):
    for pin in target_pins:
        if _last_sent.get(pin) == us:
            continue
        _last_sent[pin] = us
    for pin in target_pins:
        try:
            lgpio.tx_servo(Precharge.h, pin, us)
        except:
            pass

def manual_sweep(start_us, end_us, target_pins, custom_delay=None, step_size=5):
    if start_us == end_us:
        set_pwm(end_us, target_pins)
        return

    delay = SWEEP_DELAY if custom_delay is None else custom_delay
    step = step_size if end_us > start_us else -step_size
    current_us = start_us

    while True:
        set_pwm(current_us, target_pins)
        time.sleep(delay)

        if (step > 0 and current_us + step >= end_us) or (step < 0 and current_us + step <= end_us):
            break

        current_us += step

    set_pwm(end_us, target_pins)

def SPIN_START():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM1, PWM2]

        set_pwm(LOW, pins)
        time.sleep(0.5)

        manual_sweep(LOW, INIT, pins, step_size=5)
        time.sleep(1.5)

        manual_sweep(INIT, HIGH, pins, step_size=5)
        time.sleep(10.0)

        manual_sweep(HIGH, LOW, pins, step_size=5)

    finally:
        try:
            lgpio.tx_servo(Precharge.h, PWM1, 0)
            lgpio.tx_servo(Precharge.h, PWM2, 0)
        except:
            pass

def SPIN_TOP():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM1]

        set_pwm(LOW, pins)
        time.sleep(0.5)

        manual_sweep(LOW, INIT, pins, step_size=5)
        time.sleep(1.5)

        manual_sweep(INIT, HIGH, pins, step_size=5)
        time.sleep(3.0)

        manual_sweep(HIGH, LOW, pins, step_size=5)

    finally:
        try:
            lgpio.tx_servo(Precharge.h, PWM1, 0)
        except:
            pass

def SPIN_BOT():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM2]

        set_pwm(LOW, pins)
        time.sleep(0.5)

        manual_sweep(LOW, INIT, pins, step_size=5)
        time.sleep(1.5)

        manual_sweep(INIT, HIGH, pins, step_size=5)
        time.sleep(3.0)

        manual_sweep(HIGH, LOW, pins, step_size=5)

    finally:
        try:
            lgpio.tx_servo(Precharge.h, PWM2, 0)
        except:
            pass

def SPIN_PROP():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM1, PWM2]

        set_pwm(LOW, pins)
        time.sleep(0.5)

        manual_sweep(LOW, INIT, pins, step_size=5)
        time.sleep(1.5)

        manual_sweep(INIT, HIGHER, pins, step_size=5)

        time.sleep(30.0)

        manual_sweep(HIGHER, INIT, pins, step_size=5)

        PULSE_MAX = HIGHER + 50

        for _ in range(4):
            manual_sweep(INIT, PULSE_MAX, pins, custom_delay=0.005, step_size=5)
            time.sleep(5.0)

            manual_sweep(PULSE_MAX, INIT, pins, custom_delay=0.005, step_size=5)
            time.sleep(0.5)

    finally:
        try:
            lgpio.tx_servo(Precharge.h, PWM1, 0)
            lgpio.tx_servo(Precharge.h, PWM2, 0)
        except:
            pass