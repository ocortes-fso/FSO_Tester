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

# Define list for the 12x12 loop
# Combined list for 12x12 logic
all_pins_list = [PIN_1, PIN_2, PIN_3, PIN_4, PIN_5, PIN_6, PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12]

# Create output matrix -> 12x12 matrix all zeros initially
output_matrix = np.zeros((12, 12), dtype=int)
# pass_matrix initialized as all zeros for you to fill
pass_matrix = np.array([
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0],
    [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0]])
   
    

# Setup: Clear all pins and set them as INPUT initially
for pin in all_pins_list:
    try:
        lgpio.gpio_free(h, pin)
    except:
        pass
    lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_DOWN)

#Main Logic
try:
    for i in range(len(all_pins_list)):
        currentPin = all_pins_list[i]

        # --- FLAG: Switch current test pin to OUTPUT HIGH ---
        lgpio.gpio_free(h, currentPin)
        lgpio.gpio_claim_output(h, currentPin, 1)
        
        time.sleep(0.01) # Small delay to allow state to stabilize

        for j in range(len(all_pins_list)):
            if i == j: 
                continue # Skip self-testing to match your C logic

            testPin = all_pins_list[j]
            # Read input pin state
            # --- FLAG: Line 56 fix - testPin is guaranteed to be claimed as input ---
            if lgpio.gpio_read(h, testPin) == 1:
                output_matrix[i, j] = 1
        
        # --- FLAG: Switch current test pin back to INPUT for the next round ---
        lgpio.gpio_free(h, currentPin)
        lgpio.gpio_claim_input(h, currentPin, lgpio.SET_PULL_DOWN)

    print(output_matrix)

    if np.array_equal(output_matrix, pass_matrix):
        print("Pass")   
    else:
        print("Fail!")

finally:
    # Release the chip and pins
    for pin in all_pins_list:
        try:
            lgpio.gpio_free(h, pin)
        except:
            pass
    lgpio.gpiochip_close(h)