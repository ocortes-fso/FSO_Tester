# FSO_Tester
Repository of all the codes used for the testing boxes.

## Needs
- Disable CE1_SPIO (GPIO07)
- Add add to "/boot/firmware/config.txt" the following string: under all dtoverlay=mcp2515-can0
- Enable I2C
- Static IP has to be set on 144 gateway

## Used Libraries

1. PyMavlink     
2. lgpio         
3. NumPy         
4. Pyserial      
5. smbus2        
6. ttkbootstrap  
7. OpenCv        
8. can           
9. Pillow        