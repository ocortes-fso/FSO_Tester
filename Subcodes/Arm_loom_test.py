import time
import lgpio
import numpy as np

# GPIO pin setup
PIN_1, PIN_2, PIN_3, PIN_4, PIN_5, PIN_6 = 7, 0, 5, 12, 6, 1
PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12 = 13, 19, 16, 26, 20, 21
all_pins_list = [PIN_1, PIN_2, PIN_3, PIN_4, PIN_5, PIN_6, PIN_7, PIN_8, PIN_9, PIN_10, PIN_11, PIN_12]

def arm_loom():
    h = lgpio.gpiochip_open(4)
    output_matrix = np.zeros((12, 12), dtype=int)

    try:
        # Initial Setup: Everyone as Input
        for pin in all_pins_list:
            try: lgpio.gpio_free(h, pin)
            except: pass
            lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_DOWN)

        # Main Scan Logic
        for i in range(len(all_pins_list)):
            currentPin = all_pins_list[i]

            # Toggle current pin to Output HIGH
            lgpio.gpio_free(h, currentPin)
            lgpio.gpio_claim_output(h, currentPin, 1)
            time.sleep(0.01)

            for j in range(len(all_pins_list)):
                if i == j:# Skip self-test to match pass_matrix
                    output_matrix[i, j] = 1
                if lgpio.gpio_read(h, all_pins_list[j]) == 1:
                    output_matrix[i, j] = 1
            
            # Toggle back to Input
            lgpio.gpio_free(h, currentPin)
            lgpio.gpio_claim_input(h, currentPin, lgpio.SET_PULL_DOWN)
        print(output_matrix)
        return output_matrix
        

    finally:
        lgpio.gpiochip_close(h)