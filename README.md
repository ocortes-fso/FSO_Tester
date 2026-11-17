# FSO_Tester
Repository of all the codes used for the testing boxes.

## Setup
1. Use "sudo nano /boot/firmware/config.txt" and add the following strings: 
    - under all:
        - "dtoverlay=mcp2515-can0, oscillator=16000000, interrupt=4, spimaxfrequency=10000000"
        - "enable_uart=1"
        - "dtoverlay=spi0-1cs"
2. Use "sudo nano /boot/firmware/cmdline.txt" to remove the following string:
    - "console=serial0,115200 "
3. Enable I2C
4. Enable SPI
5. Enable Serial Port
6. Use "sudo nmtui" to;
    - Navigate to "Edit a connection"
    - Select "Wired connection 1"
    - Set "IPv4 CONFIGURATION" as "Manual"
    - Set "Adresses" to "192.168.144.200"
    - Set "Gateway" to "192.168.144.1"

## Pins and Connections
- Plug in the HAT with a 40Pin 20mm header.
- Plug the UART JST from the raspi to the Molex 3 Pin "UART" on the board.
- Plug the touchscreen to the CAM/DISP 1 or 0.

## Used Libraries
Normally Preinstallded
1. NumPy
2. lgpio
3. Pyserial
4. smbus2

Not Normally Preinstalled:
1. PyMavlink
2. tkbootstrap        
3. python-can           
4. Pillow
5. DroneCAN

- If when using pip there is an error "externally-managed-environment", use "pip install --break-system-packages package-name"

## Program Setup
After installation of all libraries:
 1. "cd Desktop"
 2. "git clone https://github.com/ocortes-fso/FSO_Tester.git"
 3. "cd"
 4. "mkdir -p ~/.config/autostart"
 5. "sudo nano ~/.config/autostart/fsotester.desktop"
 6. Add the next lines:
       ```
       [Desktop Entry]
       Type=Application
       Name=FSO Tester
       Exec=python3 /home/fso/Desktop/FSO_Tester/GUI/MasterUI.py
       X-GNOME-Autostart-enabled=true
       ```
 7. Save
       
