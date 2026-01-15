import time
import numpy as np
from gpiozero import Button, DigitalOutputDevice

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

# Input pins
# Using Button is the most stable way on Pi 5. 
# pull_up=True means the pin is 3.3V by default.
pin_1 = Button(PIN_1, pull_up=True)
pin_2 = Button(PIN_2, pull_up=True)
pin_3 = Button(PIN_3, pull_up=True)
pin_4 = Button(PIN_4, pull_up=True)
pin_5 = Button(PIN_5, pull_up=True)
pin_6 = Button(PIN_6, pull_up=True)

# Output pins
pin_7 = DigitalOutputDevice(PIN_7)
pin_8 = DigitalOutputDevice(PIN_8)
pin_9 = DigitalOutputDevice(PIN_9)
pin_10 = DigitalOutputDevice(PIN_10)
pin_11 = DigitalOutputDevice(PIN_11)
pin_12 = DigitalOutputDevice(PIN_12)

# Create output matrix -> 6x6 matrix all zeros
output_matrix = np.zeros((6, 6), dtype=int)
pass_matrix = np.array([
    [1, 0, 0, 0, 0, 0],
    [0, 1, 0, 1, 0, 0],
    [0, 0, 1, 0, 0, 0],                 ##Check this is correct for pass condition
    [0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 1, 0],
    [0, 0, 0, 0, 0, 1]])

# Main Logic
input_pins = [pin_1, pin_2, pin_3, pin_4, pin_5, pin_6]
output_pins = [pin_7, pin_8, pin_9, pin_10, pin_11, pin_12]

for i, pin_out_obj in enumerate(output_pins):
    pin_out_obj.on()  # Activate output pin HIGH
    time.sleep(0.1) 

    for j, pin_in_obj in enumerate(input_pins):
        # On Pi 5 with pull_up=True, .value is 0 when the pin is HIGH 
        # (pushed by our output) and 1 when idle. 
        # We use 'not pin_in_obj.is_pressed' to catch the HIGH signal.
        if pin_in_obj.is_pressed: 
            output_matrix[i,j] = 0
        else:
            output_matrix[i,j] = 1

    pin_out_obj.off()  # Reset output pin to low

print(output_matrix)

if np.array_equal(output_matrix, pass_matrix):
    print("Pass")   
else:
    print("Short Detected!")