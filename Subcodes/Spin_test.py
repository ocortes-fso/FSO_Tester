import time
import lgpio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import Precharge

FREQ = 400

PWM1 = 7
PWM2 = 5

LOW = 1000
INIT = 1100
HIGH = 1300
HIGHER = 1600

PUNCH_INCREMENT = 50
PUNCH_NUM = 7

INIT_DELAY = 5

START_RUN_DELAY = 7
TOP_RUN_DELAY = 4
BOT_RUN_DELAY = 4

PROP_EXTENDED_DELAY = 12
PROP_PULSE_HOLD_DELAY = 4
PROP_PULSE_PAUSE_DELAY = 1

SWEEP_DELAY = 0.005
PUNCH_SWEEP_DELAY = 0.0005
STEP_SIZE = 2.  #cannot be zero.. obviously

_last_sent = {}
_stop_event = None


def register_stop_event(event):
    global _stop_event
    _stop_event = event


def spin_stopped():
    return _stop_event is not None and _stop_event.is_set()


def safe_sleep(duration, interval=0.01):
    end_time = time.time() + duration

    while time.time() < end_time:
        if spin_stopped():
            return True

        remaining = end_time - time.time()
        time.sleep(min(interval, remaining))

    return False


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
            lgpio.tx_servo(Precharge.h, pin, us, FREQ)
        except:
            pass


def manual_sweep(start_us, end_us, pins, delay=None, step_size=STEP_SIZE):

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

        if (step > 0 and current + step >= end_us) or \
           (step < 0 and current + step <= end_us):
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

        manual_sweep(LOW, HIGH, pins)

        if safe_sleep(START_RUN_DELAY):
            return

        manual_sweep(HIGH, LOW, pins)

    finally:
        SPIN_STOP()


def SPIN_TOP():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM1]

        manual_sweep(LOW, HIGH, pins)

        if safe_sleep(TOP_RUN_DELAY):
            return

        manual_sweep(HIGH, LOW, pins)

    finally:
        SPIN_STOP()


def SPIN_BOT():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM2]

        manual_sweep(LOW, HIGH, pins)

        if safe_sleep(BOT_RUN_DELAY):
            return

        manual_sweep(HIGH, LOW, pins)

    finally:
        SPIN_STOP()


def SPIN_PROP():
    try:
        if Precharge.h is None:
            return

        claim_pwm_pins()
        pins = [PWM1, PWM2]

        manual_sweep(LOW, HIGHER, pins)

        if safe_sleep(PROP_EXTENDED_DELAY):
            return

        manual_sweep(HIGHER, LOW, pins)

        for i in range(PUNCH_NUM):

            if spin_stopped():
                return

            pulse_val = HIGHER + ((i + 1) * PUNCH_INCREMENT)

            manual_sweep(
                LOW,
                pulse_val,
                pins,
                delay=PUNCH_SWEEP_DELAY
            )

            if safe_sleep(PROP_PULSE_HOLD_DELAY):
                return

            manual_sweep(
                pulse_val,
                LOW,
                pins,
                delay=PUNCH_SWEEP_DELAY
            )

            if safe_sleep(PROP_PULSE_PAUSE_DELAY):
                return

    finally:
        SPIN_STOP()


def SPIN_STOP():
    try:
        lgpio.tx_servo(Precharge.h, PWM1, 0)
        lgpio.tx_servo(Precharge.h, PWM2, 0)

        _last_sent.pop(PWM1, None)
        _last_sent.pop(PWM2, None)

    except:
        pass

def SPIN_CNCL():
    try:
        lgpio.tx_servo(Precharge.h, PWM1, INIT)
        lgpio.tx_servo(Precharge.h, PWM2, INIT)

    except:
        pass

def SPIN_INIT():                #should see no spin just stop beeping when pressed and holds for 5 seconds, sets to 1100 then holds for 5 seconds, then sets low  
    try:
        if Precharge.h is None:
            return

        lgpio.tx_servo(Precharge.h, PWM1, INIT)
        lgpio.tx_servo(Precharge.h, PWM2, INIT)

        if safe_sleep(INIT_DELAY):
            lgpio.tx_servo(Precharge.h, PWM1, LOW)
            lgpio.tx_servo(Precharge.h, PWM2, LOW)
            return

    finally:
        SPIN_STOP()

def get_pwm_state():
    return {
        "PWM1": _last_sent.get(PWM1, None),
        "PWM2": _last_sent.get(PWM2, None)
    }