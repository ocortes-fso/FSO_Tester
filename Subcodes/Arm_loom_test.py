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
    # lgpio.SET_PULL_DOWN mimics GPIO.PUD_DOWN from RPI.GPIO library 
    # This ensures the pin is 0 until your output drives it HIGH
    # --- CHANGE 1: Added free to ensure "Busy" status is cleared ---
    lgpio.gpio_free(h, pin)
    lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_DOWN)

# --- CHANGE 2: Removed the initial output claim loop to prevent bridge conflicts ---

#Create output matrix -> 6x6 matrix all zeros instially
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

        # --- CHANGE 3: Claim output pin HIGH only when testing it ---
        lgpio.gpio_claim_output(h, pin_in_physical, 1) # Activate output pin HIGH
        time.sleep(0.1)  # Short delay to allow state to stabilize

        for j, pin_out_physical in enumerate(input_pins_list):
            output_matrix[i, j] = lgpio.gpio_read(h, pin_out_physical)  # Read input pin state, and store in matrix against output states
        
        # --- CHANGE 4: Free the pin immediately after reading ---
        lgpio.gpio_write(h, pin_in_physical, 0)  # Reset output pin to low after reading all inputs
        lgpio.gpio_free(h, pin_in_physical)

    print(output_matrix)

    if np.array_equal(output_matrix, pass_matrix):
        print("Pass")   
    else:
        print("Fail!")

finally:
    # Release the chip and pins not sure if this is needed
    # --- CHANGE 5: Added cleanup loop for input pins ---
    for pin in input_pins_list:
        try:
            lgpio.gpio_free(h, pin)
        except:
            pass
    lgpio.gpiochip_close(h)