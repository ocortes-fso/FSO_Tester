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
all_pins_list = [PIN_1, PIN_2, PIN_3, PIN_4, PIN_5, PIN_6, PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12]

# Create output matrix -> 12x12 matrix all zeros initially
output_matrix = np.zeros((12, 12), dtype=int)
pass_matrix = np.array([
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]])

#Main Logic
try:
    # This loop follows your C logic: Test connections for each pin
    for i in range(len(all_pins_list)):
        currentPin = all_pins_list[i]

        # Initialize all pins as INPUT with PULL_DOWN (like your INPUT_PULLUP reset)
        for p in all_pins_list:
            try:
                lgpio.gpio_free(h, p)
                lgpio.gpio_claim_input(h, p, lgpio.SET_PULL_DOWN)
            except:
                pass

        # Set the current pin as OUTPUT and HIGH
        lgpio.gpio_free(h, currentPin) # Free from input mode first
        lgpio.gpio_claim_output(h, currentPin, 1)
        time.sleep(0.01) # Small delay for stabilization

        # Check connections to all other pins
        for j in range(len(all_pins_list)):
            if i == j: 
                continue # Skip self-testing to match your C logic 'if (i == j) continue'

            testPin = all_pins_list[j]
            if lgpio.gpio_read(h, testPin) == 1:
                output_matrix[i, j] = 1

        # Reset the current pin (Freeing it acts like setting back to INPUT)
        lgpio.gpio_free(h, currentPin)

    # Output results
    print(output_matrix)

    if np.array_equal(output_matrix, pass_matrix):
        print("Pass")   
    else:
        print("Fail!")

finally:
    # Final cleanup for the chip
    lgpio.gpiochip_close(h)