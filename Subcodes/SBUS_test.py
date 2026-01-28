import serial  #need pyserial module 

#config uart for SBUS and open serial port 

SBUS = serial.Serial(
    port="/dev/ttyAMA10",       # debug pi5 serial port - used for SBUS
    baudrate = 115200,          
    bytesize = serial.EIGHTBITS,
    parity = serial.PARITY_EVEN,
    stopbits = serial.STOPBITS_TWO,
    timeout = 0.02
)


SBUS_frame_length = 25  #SBUS frame length in bytes (standard SBUS frame length)
SBUS_header = 0x0F     #SBUS frame header byte (standard SBUS starting byte)

while True:
    
    # This prevents the serial read from crashing the whole loop if it fails to detect the frame
    try:
        frame = SBUS.read(SBUS_frame_length)  #read SBUS frame
    except serial.SerialException as e:
        print(f"Error reading SBUS: {e}")
        continue
    
    # read and verify valid SBUS frames are being received
    if len(frame) == SBUS_frame_length and frame[0] == SBUS_header:
        print("SBUS Connected **PASS**")
    else:
        print("SBUS not detected **FAIL**")

#close serial port (SBUS) -- will not loop
          
SBUS.close()