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
# all pins list for new 12x12 matrix logic
all_pins_list = [PIN_1, PIN_2, PIN_3, PIN_4, PIN_5, PIN_6, PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12]

# Create output matrix -> 12x12 matrix all zeros initially
output_matrix = np.zeros((12, 12), dtype=int)
# pass_matrix 
pass_matrix = np.array([
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0],
    [0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0],
    [0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],])
#Main Logic
try:
    for i, pin_drive in enumerate(all_pins_list):
        
        # Ensure all other pins are set as inputs before driving the current pin
        for other_pin in all_pins_list:
            if other_pin != pin_drive:
                try:
                    lgpio.gpio_free(h, other_pin)
                    lgpio.gpio_claim_input(h, other_pin, lgpio.SET_PULL_DOWN)
                except:
                    pass

        # Claim the pin HIGH right here 
        lgpio.gpio_claim_output(h, pin_drive, 1) 
        
        time.sleep(0.1)  # Short delay to allow state to stabilize

        for j, pin_read in enumerate(all_pins_list):
            output_matrix[i, j] = lgpio.gpio_read(h, pin_read)  # Read input pin state
        
        # Free the pin immediately after reading 
        lgpio.gpio_free(h, pin_drive)

    print(output_matrix)

    if np.array_equal(output_matrix, pass_matrix):
        print("Pass")   
    else:
        print("Fail!")

finally:
    # Release the chip and pins not sure if this is needed
    for pin in all_pins_list:
        try:
            lgpio.gpio_free(h, pin)
        except:
            pass
    lgpio.gpiochip_close(h)