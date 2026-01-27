# Test network connection of H16P via simple ping, and also fetch single video frame from MIPI cam
import time
import subprocess

H16P_IP = "192.168.144.10" 
Num_pings = "10" 
RTSP = "rtsp://192.168.43.1:8554/fpv_stream"


# Global capture object to keep stream open
fpv = None

def ping():
    result  = subprocess.run(['ping', '-c', Num_pings, H16P_IP], stdout=subprocess.PIPE)
    if result.returncode == 0:
        time.sleep(2)
        return True
    else:
        time.sleep(2)
        return False
