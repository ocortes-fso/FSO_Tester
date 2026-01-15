import time
from gpiozero import DigitalInputDevice, DigitalOutputDevice #this should work with pi5
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

# gpiozero handles setmode(BCM) automatically

#Input pins
# pull_up=True mimics GPIO.PUD_UP. 
# In gpiozero, .value will return 0 when the button is pulled HIGH and 1 when pulled LOW.
pin_1 = DigitalInputDevice(PIN_1, pull_up=False)
pin_2 = DigitalInputDevice(PIN_2, pull_up=False)
pin_3 = DigitalInputDevice(PIN_3, pull_up=False)
pin_4 = DigitalInputDevice(PIN_4, pull_up=False)
pin_5 = DigitalInputDevice(PIN_5, pull_up=False)
pin_6 = DigitalInputDevice(PIN_6, pull_up=False)

#Output pins
pin_7 = DigitalOutputDevice(PIN_7)
pin_8 = DigitalOutputDevice(PIN_8)
pin_9 = DigitalOutputDevice(PIN_9)
pin_10 = DigitalOutputDevice(PIN_10)
pin_11 = DigitalOutputDevice(PIN_11)
pin_12 = DigitalOutputDevice(PIN_12)

#Create output matrix -> 6x6 matrix all zeros
output_matrix = np.zeros((6, 6), dtype=int)
pass_matrix = np.array([
    [1, 0, 0, 0, 0, 0],
    [0, 1, 0, 1, 0, 0],
    [0, 0, 1, 0, 0, 0],                 ##Check this is correct for pass condition
    [0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 1, 0],
    [0, 0, 0, 0, 0, 1]])

#Main Logic
# Grouping objects into lists for the loops
input_pins = [pin_1, pin_2, pin_3, pin_4, pin_5, pin_6]
output_pins = [pin_7, pin_8, pin_9, pin_10, pin_11, pin_12]

for i, pin_in in enumerate(output_pins):
    pin_in.on()  # Activate output pin HIGH
    time.sleep(0.1)  # Short delay to allow state to stabilize

    for j, pin_out in enumerate(input_pins):
        # We use .value to read the state. 
        # Note: with pull_up=True, .value is 0 when HIGH and 1 when LOW.
        output_matrix[i,j] = pin_out.value  # Read input pin state, and store in matrix against output states

    pin_in.off()  # Reset output pin to low after reading all inputs

print(output_matrix)

if np.array_equal(output_matrix, pass_matrix):
    print("Pass")   
else:
    print("Short Detected!")

# gpiozero cleans up automatically when the script ends