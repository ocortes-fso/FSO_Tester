#Test network connection of H16P via simple ping

import time
import os
import subprocess
from pyroute2 import IPDB
from pyroute2 import IPRoute


#Set static IP to be on 144 network class

interface = 'eth0' #need to check this but this should be the ethernet of the pi5
static_ip = '192.168.144.200/24' #static IP of the ethernet adaptor for the pi5 -- must be on 144 network class
gateway_ip = '192.168.144.1' #gateway address

with IPDB() as ipdb:
    iface = ipdb.interfaces[interface]
    iface.add_ip(static_ip)
    iface.up().commit()
    ipdb.routes.add({'dst': 'default', 'gateway': gateway_ip}).commit()
    
    
time.sleep(2)  #wait for settings to take effect
    
#Ping test to verify network connection

IP = "192.168.144.100" #H16Pro air unit IP on the network
Num_pings = "10" 

result  = subprocess.run(['ping', '-c', Num_pings, IP], stdout=subprocess.PIPE)

if result.returncode == 0:  #deffualt linux ping return code for success - atleast one code recieved
    print("PASS! Network Test Passed: H16Pro receiver is reachable.")
else:
    print("Network Test Failed: H16Pro reciever is not reachable.")
    
    
    
##do we want to actually display the ping outputs or just a pass/fail message?