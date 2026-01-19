# Test network connection of H16P via simple ping
import time
import os
import subprocess
import cv2
from PIL import Image

H16P_IP = "192.168.144.100" 
Num_pings = "10" 
RTSP = "rtsp://192.168.43.1:8554/fpv_stream"

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;5000000"

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
        # If open fails, reset to try again later
        fpv = None
    return None