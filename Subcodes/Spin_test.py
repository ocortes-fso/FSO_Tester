import time
import lgpio

PWM1 = 7
PWM2 = 5
CHIP = 4

INIT = 1140
HIGH = 1250
HIGHER = 1350
LOW = 1000
SWEEP_DELAY = 0.0005


def set_pwm(h, freq, target_pins):
    for pin in target_pins:
        lgpio.tx_pwm(h, pin, freq, 500000)


def manual_sweep(h, start_freq, end_freq, target_pins, custom_delay=SWEEP_DELAY):
    step = 1 if end_freq > start_freq else -1
    for freq in range(start_freq, end_freq + step, step):
        set_pwm(h, freq, target_pins)
        time.sleep(custom_delay)

#call for normal spin test NO PROPS!!

def SPIN():
    try:
        h = lgpio.gpiochip_open(CHIP)
        pins = [PWM1, PWM2]
        for pin in pins:
            lgpio.gpio_claim_output(h, pin)

        manual_sweep(h, LOW, INIT, pins)
        time.sleep(1.0)

        manual_sweep(h, INIT, HIGH, pins)
        time.sleep(5.0)

        manual_sweep(h, HIGH, LOW, pins)

    except Exception as e:
        pass
    finally:
        if "h" in locals():
            lgpio.tx_pwm(h, PWM1, 0, 0)
            lgpio.tx_pwm(h, PWM2, 0, 0)
            lgpio.gpiochip_close(h)

#call for Spin test PWM1 / TOP

def SPIN_TOP():
    try:
        h = lgpio.gpiochip_open(CHIP)
        pins = [PWM1]
        lgpio.gpio_claim_output(h, PWM1)

        manual_sweep(h, LOW, INIT, pins)
        time.sleep(1.0)

        manual_sweep(h, INIT, HIGH, pins)
        time.sleep(5.0)

        manual_sweep(h, HIGH, LOW, pins)

    except Exception as e:
        pass
    finally:
        if "h" in locals():
            lgpio.tx_pwm(h, PWM1, 0, 0)
            lgpio.gpiochip_close(h)

#call for Spin test PWM2 / BOT

def SPIN_BOT():
    try:
        h = lgpio.gpiochip_open(CHIP)
        pins = [PWM2]
        lgpio.gpio_claim_output(h, PWM2)

        manual_sweep(h, LOW, INIT, pins)
        time.sleep(1.0)

        manual_sweep(h, INIT, HIGH, pins)
        time.sleep(5.0)

        manual_sweep(h, HIGH, LOW, pins)

    except Exception as e:
        pass
    finally:
        if "h" in locals():
            lgpio.tx_pwm(h, PWM2, 0, 0)
            lgpio.gpiochip_close(h)


#call for vibration/prop spin test WITH PROPS!!
    #adjust delays if needed for ramp up 
    # 1350-1140 = 210, 210x0.2 = 42 seconds 

    #expected bahviour.. go to INIT, hold, ramp up to higher with slower ramp speed than other tests, hold, perform 3 pulses, ramp down at sweep speed


def SPIN_PROP():
    try:
        h = lgpio.gpiochip_open(CHIP)
        pins = [PWM1, PWM2]
        for pin in pins:
            lgpio.gpio_claim_output(h, pin)

        manual_sweep(h, LOW, INIT, pins)
        time.sleep(1.0)

        manual_sweep(h, INIT, HIGHER, pins, custom_delay=0.2)

        time.sleep(60.0)

        PULSE_MAX = HIGHER + 30
        for _ in range(3):
            manual_sweep(h, HIGHER, PULSE_MAX, pins, custom_delay=0.002)
            time.sleep(3.0)
            manual_sweep(h, PULSE_MAX, HIGHER, pins, custom_delay=0.002)
            time.sleep(5.0)

        manual_sweep(h, HIGHER, LOW, pins)


    except Exception as e:
        pass
    finally:
        if "h" in locals():
            lgpio.tx_pwm(h, PWM1, 0, 0)
            lgpio.tx_pwm(h, PWM2, 0, 0)
            lgpio.gpiochip_close(h)