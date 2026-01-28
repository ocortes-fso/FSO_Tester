import time
import threading
import lgpio

##### PARAMETERS #####
CHIP = 4                # GPIO CHIP number
RED_PIN = 0
GREEN_PIN = 1
BLUE_PIN = 7
SWITCH_PIN = 25
LED_SWITCH_PIN = 24

_RGB_VALUES = [(1,0,0), (0,1,0), (0,0,1)] #high on 1 others low for r, g, b

_h = None
_thread = None
_stop_event = threading.Event()

##### Internal Functions #####

def _set_rgb_colour(r, g, b):
    lgpio.gpio_write(_h, RED_PIN, r)
    lgpio.gpio_write(_h, GREEN_PIN, g)
    lgpio.gpio_write(_h, BLUE_PIN, b)

def _all_off():
    _set_rgb_colour(0, 0, 0)
    lgpio.gpio_write(_h, LED_SWITCH_PIN, 0)

def _sleep_check_stop(seconds, step=0.02):
    end = time.time() + seconds
    while time.time() < end and not _stop_event.is_set():
        time.sleep(min(step, end - time.time()))

def _run_loop():
    try:
        while not _stop_event.is_set():
            state = lgpio.gpio_read(_h, SWITCH_PIN)

            # Switch OFF (0): button LED off, status cycles RGB
            if state == 0:
                lgpio.gpio_write(_h, LED_SWITCH_PIN, 0)
                for colour in _RGB_VALUES:
                    if _stop_event.is_set():
                        break
                    _set_rgb_colour(*colour)
                    _sleep_check_stop(0.2)

            # Switch ON (1): button LED on, status blinks RED
            else:
                lgpio.gpio_write(_h, LED_SWITCH_PIN, 1)
                while (not _stop_event.is_set()) and (lgpio.gpio_read(_h, SWITCH_PIN) == 1):
                    _set_rgb_colour(0, 0, 0)
                    _sleep_check_stop(0.5)
                    _set_rgb_colour(1, 0, 0)
                    _sleep_check_stop(0.5)

            time.sleep(0.02)

    finally:
        # leave LEDs in a safe state if loop exits
        try:
            _all_off()
        except Exception:
            pass


##### External Functions #####
def start():                                # Call when GUI frame opens (or Start button)
    global _h, _thread

    if _thread and _thread.is_alive():
        return  # already running

    _stop_event.clear()

    _h = lgpio.gpiochip_open(CHIP)

    for pin in [RED_PIN, GREEN_PIN, BLUE_PIN, LED_SWITCH_PIN]:
        lgpio.gpio_claim_output(_h, pin)

    lgpio.gpio_claim_input(_h, SWITCH_PIN, lgpio.SET_PULL_NONE)

    _thread = threading.Thread(target=_run_loop, daemon=True)
    _thread.start()


def close():                                 # Call when GUI frame closes (or Stop button)
    global _h, _thread

    _stop_event.set()

    if _thread:
        _thread.join(timeout=1.0)

    if _h is not None:
        try:
            _all_off()
        except Exception:
            pass
        try:
            lgpio.gpiochip_close(_h)
        except Exception:
            pass

    _h = None
    _thread = None
