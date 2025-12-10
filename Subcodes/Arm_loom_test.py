import time
import RPi.GPIO as GPIO

# GPIO pin setup
PIN_1 = 7
PIN_2 = 2
PIN_3 = 5
PIN_4 = 12
PIN_5 = 6
PIN_6 = 1
PIN_7 = 13
PIN_8 = 19
PIN_9 = 16
PIN_10 = 26
PIN_11 = 20
PIN_12 = 21


GPIO.setmode(GPIO.BCM)

#Input pins
GPIO.setup([PIN_1,PIN_2, PIN_3, PIN_4, PIN_5, PIN_6], GPIO.IN, pull_up_down=GPIO.PUD_UP)

#Output pins
GPIO.setup([PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12], GPIO.OUT)

#Main Logic
try:
    while True:
        # Set output pins high
        GPIO.output([PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12], GPIO.HIGH)
        time.sleep(1)  

        # Read input pins and check continuity outputs 'High or Low in 1x6 matrix' state high (1) means short is detected
        input_states = [GPIO.input(pin) for pin in [PIN_1, PIN_2, PIN_3, PIN_4, PIN_5, PIN_6]]
        print("Input States (High/Low):", input_states)

        # Set output pins low
        GPIO.output([PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12], GPIO.LOW)
        time.sleep(1)  # Wait for 1 second

except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()