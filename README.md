# FSO_Tester
Repository of all the codes used for the testing boxes.

## Needs
- Disable CE1_SPIO (GPIO07)
- Add add to "/boot/firmware/config.txt" the following strings: 
    - "under all dtoverlay=mcp2515-can0"
    - "enable_uart=1"
- Remove the following string from "/boot/firmware/cmdline.txt":
    - "console=serial0,115200 "
- Enable I2C
- Static IP has to be set on 144 gateway

## Used Libraries

1. PyMavlink     
2. lgpio         
3. NumPy         
4. Pyserial      
5. smbus2        
6. ttkbootstrap        
7. python-can           
8. Pillow
9. DroneCAN  
