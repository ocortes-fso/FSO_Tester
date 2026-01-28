from Subcodes import Debug
import time

Debug.start()
Debug.set_mode_44()

try:
    while True:
        for line in Debug.read_messages():
            print(line)
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    Debug.set_mode_40()
    Debug.close()