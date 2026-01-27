# Test network connection of H16P via simple ping, and also fetch single video frame from MIPI cam
import time
import subprocess
import cv2
from PIL import Image

H16P_IP = "192.168.144.10" 
Num_pings = "10" 
RTSP = "rtsp://192.168.43.1:8554/fpv_stream"


# Global capture object to keep stream open
fpv = None

def ping():
    result  = subprocess.run(['ping', '-c', Num_pings, H16P_IP], stdout=subprocess.PIPE)
    if result.returncode == 0:
        print("PASS! Network Test Passed: H16Pro receiver is reachable.")
        return True
    else:
        print("Network Test Failed: H16Pro reciever is not reachable.")
        return False

def cam():
    global fpv
    # Initialize if not already open
    if fpv is None or not fpv.isOpened():
        fpv = cv2.VideoCapture(RTSP)
    
    if fpv.isOpened():
        ret, frame = fpv.read()
        if ret and frame is not None:
            return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    else:
        # If open fails return none, rety is handled through the GUI
        fpv = None
    return None