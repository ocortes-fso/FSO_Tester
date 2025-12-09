import time
import RPi.GPIO as GPIO

# GPIO pin setup
RED_PIN = 0
GREEN_PIN = 1
BLUE_PIN = 7

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.OUT)

# PWM for brightness control
red_pwm = GPIO.PWM(RED_PIN, 1000)
green_pwm = GPIO.PWM(GREEN_PIN, 1000)
blue_pwm = GPIO.PWM(BLUE_PIN, 1000)

red_pwm.start(0)
green_pwm.start(0)
blue_pwm.start(0)

def set_color(r, g, b):
    red_pwm.ChangeDutyCycle(r)
    green_pwm.ChangeDutyCycle(g)
    blue_pwm.ChangeDutyCycle(b)

colours = [(100, 0, 0), (0, 100, 0), (0, 0, 100)] 
delay = 1

try:
    while True:
        for r, g, b in colours:
            set_color(r, g, b)
            time.sleep(delay)
except KeyboardInterrupt:
    pass
finally:
    red_pwm.stop()
    green_pwm.stop()
    blue_pwm.stop()
    GPIO.cleanup()
