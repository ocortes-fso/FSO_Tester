# Test network connection of H16P via simple ping, and also fetch single video frame from MIPI cam
import time
import subprocess
import os

H16P_IP = "192.168.144.10" 
Num_pings = "10" 
RTSP = "rtsp://192.168.43.1:8554/fpv_stream"


def ping():
    result  = subprocess.run(['ping', '-c', Num_pings, H16P_IP], stdout=subprocess.PIPE)
    if result.returncode == 0:
        return True
    else:
        return False
