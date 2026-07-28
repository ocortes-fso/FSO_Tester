import time
import lgpio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import Precharge

PWM1 = 7
PWM2 = 5

INIT = 1100   #need to confirm these values..
HIGH = 1280
HIGHER = 1400
LOW = 1000
SWEEP_DELAY = 0.02

_last_sent = {}

_stop_event = None

def register_stop_event(event):
    global _stop_event
    _stop_event = event

def spin_stopped():
    return _stop_event is not None and _stop_event.is_set()

def claim_pwm_pins():
    try:
        lgpio.gpio_claim_output(Precharge.h, PWM1, level=0)
    except:
        pass
    try:
        lgpio.gpio_claim_output(Precharge.h, PWM2, level=0)
    except:
        pass

def set_pwm(us, pins):
    for pin in pins:
        if _last_sent.get(pin) == us:
            continue
        _last_sent[pin] = us
        try:
            lgpio.tx_servo(Precharge.h, pin, us)
        except:
            pass

def safe_sleep(duration):
    step = 0.01
    elapsed = 0
    while elapsed < duration:
        if spin_stopped():
            return True
        time.sleep(step)
        elapsed += step
    return False

def manual_sweep(start_us, end_us, pins, delay=None, step_size=2):
    if start_us == end_us:
        set_pwm(end_us, pins)
        return

    delay = SWEEP_DELAY if delay is None else delay
    step = step_size if end_us > start_us else -step_size
    current = start_us

    while True:
        if spin_stopped():
            return

        set_pwm(current, pins)

        if safe_sleep(delay):
            return

        if (step > 0 and current + step >= end_us) or (step < 0 and current + step <= end_us):
            break

        current += step

    if not spin_stopped():
        set_pwm(end_us, pins)

def SPIN_START():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM1, PWM2]

        set_pwm(LOW, pins)
        if safe_sleep(0.5): return

        manual_sweep(LOW, HIGH, pins)
        if safe_sleep(10.0): return

        manual_sweep(HIGH, LOW, pins)

    finally:
        SPIN_STOP()

def SPIN_TOP():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM1]

        set_pwm(LOW, pins)
        if safe_sleep(0.5): return

        manual_sweep(LOW, HIGH, pins)
        if safe_sleep(3.0): return

        manual_sweep(HIGH, LOW, pins)

    finally:
        SPIN_STOP()

def SPIN_BOT():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM2]

        set_pwm(LOW, pins)
        if safe_sleep(0.5): return

        manual_sweep(LOW, HIGH, pins)
        if safe_sleep(3.0): return

        manual_sweep(HIGH, LOW, pins)

    finally:
        SPIN_STOP()

def SPIN_PROP():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM1, PWM2]

        set_pwm(LOW, pins)
        if safe_sleep(0.5): return

        manual_sweep(LOW, INIT, pins)
        if safe_sleep(1.5): return

        manual_sweep(INIT, HIGHER, pins)
        if safe_sleep(30.0): return

        manual_sweep(HIGHER, INIT, pins)

        step_increment = 50
        pulse_count = 5

        for i in range(pulse_count):
            if spin_stopped():
                return

            target_pulse = HIGHER + ((i + 1) * step_increment)

            manual_sweep(INIT, target_pulse, pins, delay=0.005)
            if safe_sleep(5.0): return

            manual_sweep(target_pulse, INIT, pins, delay=0.005)
            if safe_sleep(0.5): return

    finally:
        SPIN_STOP()

def SPIN_STOP():
    global _last_sent
    _last_sent.clear()
    try:
        lgpio.tx_servo(Precharge.h, PWM1, 0)
        lgpio.tx_servo(Precharge.h, PWM2, 0)
    except:
        pass