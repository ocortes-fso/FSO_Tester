import time
import lgpio
import numpy as np

# GPIO pin setup
PIN_1 = 7
PIN_2 = 0
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

# Open the gpiochip (Pi 5 uses chip 4 for the RP1 GPIOs)
h = lgpio.gpiochip_open(4)

# Define lists for the loops
# Input pins
input_pins_list = [PIN_1, PIN_2, PIN_3, PIN_4, PIN_5, PIN_6]
# Output pins
output_pins_list = [PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12]

# Setup pins
for pin in input_pins_list:
    # lgpio.SET_PULL_DOWN mimics GPIO.PUD_DOWN
    # This ensures the pin is 0 until your output drives it HIGH
    lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_DOWN)

for pin in output_pins_list:
    lgpio.gpio_claim_output(h, pin)

#Create output matrix -> 6x6 matrix all zeros
output_matrix = np.zeros((6, 6), dtype=int)
pass_matrix = np.array([
    [1, 0, 0, 0, 0, 0],
    [0, 1, 0, 1, 0, 0],
    [0, 0, 1, 0, 0, 0],            
    [0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 1, 0],
    [0, 0, 0, 0, 0, 1]])

#Main Logic
try:
    for i, pin_in_physical in enumerate(output_pins_list):
        if i == 1 or i == 3:
            lgpio.gpio_write(h, 1, 1)  # Activate output pin HIGH
            lgpio.gpio_write(h, 3, 1)  # Activate output pin HIGH
            time.sleep(0.1)  # Short delay to allow state to stabilize
        else:
            lgpio.gpio_write(h, pin_in_physical, 1)  # Activate output pin HIGH
            time.sleep(0.1)  # Short delay to allow state to stabilize

        for j, pin_out_physical in enumerate(input_pins_list):
            output_matrix[i,j] = lgpio.gpio_read(h, pin_out_physical)  # Read input pin state, and store in matrix against output states
        
        for y, pin_in_physical in enumerate(output_pins_list):
            lgpio.gpio_write(h, pin_in_physical, 0)  # Reset output pin to low after reading all inputs

    print(output_matrix)

    if np.array_equal(output_matrix, pass_matrix):
        print("Pass")   
    else:
        print("Short Detected!")

finally:
    # Release the chip and pins
    lgpio.gpiochip_close(h)

##added elsif statements eg short on pin 2 ect