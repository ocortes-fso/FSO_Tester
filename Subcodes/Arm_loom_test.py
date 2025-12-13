import time
import RPi.GPIO as GPIO
import numpy as np

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

#Create output matrix -> 6x6 matrix all zeros
output_matrix = np.zeros((6, 6), dtype=int)
pass_matrix = np.array(

[[1 0 0 0 0 0]
 [0 1 0 1 0 0]
 [0 0 1 0 0 0]
 [0 1 0 1 0 0]
 [0 0 0 0 1 0]
 [0 0 0 0 0 1]])

#Main Logic
for i, pin_in in enumerate([PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12]):
    GPIO.output(pin_in, GPIO.HIGH)  # Activate output pin HIGH
    time.sleep(0.1)  # Short delay to allow state to stabilize

    for j, pin_out in enumerate([PIN_1, PIN_2, PIN_3, PIN_4, PIN_5, PIN_6]):
        output_matrix[i,j] = GPIO.input(pin_out)  # Read input pin state, and store in matrix against output states

    GPIO.output(pin_in, GPIO.LOW)  # Reset output [in to low after reading all inputs

print(output_matrix)

if np.array_equal(output_matrix, pass_matrix):
    print("Pass")   
else:
    print("Short Detected!")

    GPIO.cleanup()
