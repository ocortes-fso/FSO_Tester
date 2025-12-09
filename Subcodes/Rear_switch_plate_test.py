import time
import RPi.GPIO as GPIO

# GPIO pin setup
RED_PIN = 0
GREEN_PIN = 1
BLUE_PIN = 7
SWITCH_PIN = 25
LED_SWITCH_PIN = 42


# Initialize and setup GPIO
GPIO.setmode(GPIO.BCM)

#RGB LED pins
GPIO.setup([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.OUT)


#Switch pins
GPIO.setup([SWITCH_PIN, LED_SWITCH_PIN], GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(LED_SWITCH_PIN, GPIO.OUT)


#Main Logic

def set_rgb_colour(r, g, b):
    GPIO.output(RED_PIN, r)
    GPIO.output(GREEN_PIN, g)
    GPIO.output(BLUE_PIN, b)

def cycle_rgb():
    colours = [
        (1,0,0),  # Red
        (0,1,0),  # Green   
        (0,0,1),  # Blue
    ]
    

while True:
    
    #Switch off - power button LED off, status LED cycles RGB  
    colours = [0, 0, 0]
    n = 0
    if GPIO.input(SWITCH_PIN) == GPIO.low:
        GPIO.output(LED_SWITCH_PIN, GPIO.low)
        for colour in colours:
            set_rgb_colour(colours[n])
            time.sleep(1)
            n = n + 1 
        n = 0  
        
        #Switch on - power button LED on, status LED blinks RED
    elif GPIO.input(SWITCH_PIN) == GPIO.high:
         GPIO.output(LED_SWITCH_PIN, GPIO.high)
         while GPIO.input(SWITCH_PIN) == GPIO.high:
            set_rgb_colour(0, 0, 0 )
            time.sleep(0.5)
            set_rgb_colour(colours[0])
            time.sleep(0.5) 
