# FSO_Tester
Repository of all the codes used for the testing boxes.

## Setup
1. Disable CE1_SPIO (GPIO07)
2. Add add to "/boot/firmware/config.txt" the following strings: 
    - "under all dtoverlay=mcp2515-can0, oscillator=16000000, interrupt=4, spimaxfrequency=10000000" (to confirm frequency)
    - "enable_uart=1"
3. Remove the following string from "/boot/firmware/cmdline.txt":
    - "console=serial0,115200 "
4. Enable I2C
5. Enable SPI
6. Enable Serial Port
7. Static IP has to be set on 144 gateway

## Pins and Connections
- Plug in the HAT with a 40Pin 20mm header.
- Plug the UART JST from the raspi to the Molex 3 Pin "UART" on the board.
- Plug the touchscreen to the CAM/DISP 1 or 0.

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
