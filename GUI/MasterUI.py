from tkinter import BOTH, TRUE
import cv2
import ttkbootstrap as ttk 
from ttkbootstrap.constants import *
import sys
import os
from PIL import Image, ImageTk
import threading

# must have this since not in same directory as subcodes
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# import of codes used in GUI
from Subcodes import Magnetometer, Lidar, Network_test

root = ttk.Window(themename="cyborg", size=[1920,1080], title="FSO Tester") 
style = ttk.Style()
style.configure('primary.TButton', font=(None, 32, 'bold'))
style.configure('Outline.TButton', font=(None, 16, 'bold'))
style.configure('primary.TLabel', font=(None, 52, 'bold'))
style.configure('secondary.TButton', font=(None, 32, 'bold'))
style.configure('secondary.TLabel', font=(None, 28, 'bold'))
style.configure('Header.TLabel', font=(None, 32, 'bold'))
style.configure('Sub.TLabel', font=(None, 28))

# Main window/home page
main = ttk.Frame(root) 

# Frames for different test pages
lidar_f = ttk.Frame(root) 
mag_f = ttk.Frame(root)
switch_plate_f = ttk.Frame(root)
arm_f = ttk.Frame(root)
body_f = ttk.Frame(root)
volt_f = ttk.Frame(root)
SBUS_f = ttk.Frame(root)
SBUS_f_INF = ttk.Frame(root)
Eth_f = ttk.Frame(root)

# video frame
vid_f = ttk.Frame(Eth_f, width=640, height=480) # small video can change if needed but should be fine
vid_f.pack(anchor=E, expand=TRUE, padx=50, pady=50)
vid_f.pack_propagate(False)  # prevent frame from resizing to video size

# labels mag
l1 = ttk.Label(mag_f, text="Waiting for Magnetometer...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l1.pack(fill=BOTH, expand=TRUE)

# labels lidar
l2 = ttk.Label(lidar_f, text="Waiting for Lidar...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l2.pack(fill=BOTH, expand=TRUE)

# labels ethernet
l3 = ttk.Label(vid_f, text="Waitng for camera...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER) # centred to the video frame not parent window
l3.pack(fill=BOTH, expand=TRUE)

body_left_container = ttk.Frame(body_f)
body_left_container.pack(side=LEFT, fill=BOTH, expand=TRUE)

# labels body test (Stacked vertically inside the container above)
l4 = ttk.Label(body_left_container, text="SERIAL", bootstyle=SECONDARY)
l4.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

l5 = ttk.Label(body_left_container, text="ANALOG PORT", bootstyle=SECONDARY)
l5.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

l6 = ttk.Label(body_left_container, text="CAN", bootstyle=SECONDARY)
l6.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

l7 = ttk.Label(body_left_container, text="PWM", bootstyle=SECONDARY)
l7.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

# labels voltage test
volt_container = ttk.Frame(volt_f)
volt_container.pack(expand=TRUE)

l8 = ttk.Label(volt_container, text="3. SERIAL", bootstyle=SECONDARY, style='Header.TLabel')
l8.pack(pady=(20, 5))
l9 = ttk.Label(volt_container, text="A1:", bootstyle=SECONDARY, style='Sub.TLabel')
l9.pack()
l10 = ttk.Label(volt_container, text="A2:", bootstyle=SECONDARY, style='Sub.TLabel')
l10.pack()
l11 = ttk.Label(volt_container, text="A3:", bootstyle=SECONDARY, style='Sub.TLabel')
l11.pack()
l12 = ttk.Label(volt_container, text="A4:", bootstyle=SECONDARY, style='Sub.TLabel')
l12.pack()
l13 = ttk.Label(volt_container, text="4. CAN/SBUS", bootstyle=SECONDARY, style='Header.TLabel')
l13.pack(pady=(20, 5))
l14 = ttk.Label(volt_container, text="A5:", bootstyle=SECONDARY, style='Sub.TLabel')
l14.pack()
l15 = ttk.Label(volt_container, text="A6:", bootstyle=SECONDARY, style='Sub.TLabel')
l15.pack()
l16 = ttk.Label(volt_container, text="5. RC-OUT", bootstyle=SECONDARY, style='Header.TLabel')
l16.pack(pady=(20, 5))
l17 = ttk.Label(volt_container, text="A7:", bootstyle=SECONDARY, style='Sub.TLabel')
l17.pack()
l18 = ttk.Label(volt_container, text="A8:", bootstyle=SECONDARY, style='Sub.TLabel')
l18.pack()
l19 = ttk.Label(volt_container, text="6. PAYLOAD", bootstyle=SECONDARY, style='Header.TLabel')
l19.pack(pady=(20, 5))
l20 = ttk.Label(volt_container, text="A9:", bootstyle=SECONDARY, style='Sub.TLabel')
l20.pack()

#labels switch plate
l21 = ttk.Label(switch_plate_f, text="Plug in Switch Plate to test...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l21.pack(fill=BOTH, expand=TRUE)    


# main UI functions
def home():
    lidar_f.pack_forget()
    mag_f.pack_forget()
    switch_plate_f.pack_forget()
    arm_f.pack_forget()
    body_f.pack_forget()
    volt_f.pack_forget()
    SBUS_f.pack_forget()
    SBUS_f_INF.pack_forget()
    Eth_f.pack_forget()
    vid_f.pack_forget()
    main.pack(fill=BOTH, expand=TRUE)
    
def Eth():
    body_f.pack_forget()
    Eth_f.pack(fill=BOTH, expand=TRUE)
    vid_f.pack(anchor=E, expand=TRUE, padx=50, pady=50) # Ensure vid_f is visible

    def update_vid():
        # Inner function to run in a separate thread
        def fetch_frame():
            frame = Network_test.cam()
            # Use root.after to update the UI from the main thread
            root.after(0, lambda: process_frame(frame))

        def process_frame(frame):
            if frame:
                frame = frame.resize((640, 480))  
                imgtk = ImageTk.PhotoImage(frame)
                l3.imgtk = imgtk  
                l3.config(image=imgtk, text="")  
            else:
                l3.config(image="", text="Waiting for camera...")

            # Schedule next update only if Eth frame is still visible
            if Eth_f.winfo_viewable():
                root.after(40, update_vid) # Shorter delay for smoother video may need to adjust if laggy

        # Start the network-heavy task in the background in separate thread
        threading.Thread(target=fetch_frame, daemon=True).start()

    update_vid()

def lidar():
    main.pack_forget()
    lidar_f.pack(fill=BOTH, expand=TRUE)
    update_lidar()
   
def mag():
    main.pack_forget()
    mag_f.pack(fill=BOTH, expand=TRUE) 
    update_mag()  # Start the magnetometer update loop
   
def switch_plate():
    main.pack_forget()
    switch_plate_f.pack(fill=BOTH, expand=TRUE)
   
def arm():
    main.pack_forget()
    arm_f.pack(fill=BOTH, expand=TRUE)

def body():
    main.pack_forget()
    body_f.pack(fill=BOTH, expand=TRUE)    

def volt():
    main.pack_forget()
    volt_f.pack(fill=BOTH, expand=TRUE)

def SBUS_INF():
    body_f.pack_forget()
    create_sliders(SBUS_f_INF)
    SBUS_f_INF.pack(fill=BOTH, expand=TRUE)
   
def SBUS():
    body_f.pack_forget()
    SBUS_f.pack(fill=BOTH, expand=TRUE)

# Magnetometer update function
def update_mag():
    if not mag_f.winfo_viewable():
        return

    val = Magnetometer.main()
    if val:
        l1.config(text=f"X: {val[0]} \nY: {val[1]} \nZ: {val[2]} \n|B|: {val[3]:.1f}")
    else:
        l1.config(text="Waiting for Magnetometer...")

    root.after(100, update_mag)

# Lidar update function
def update_lidar():
    if not lidar_f.winfo_viewable():
        return

    distance = Lidar.read_lidar_distance()
    if distance is not None:
        l2.config(text=f"Lidar Distance: {distance} m")
    else:
        l2.config(text="Waiting for Lidar")

    root.after(100, update_lidar)

# SBUS slider function
def create_sliders(SBUS_f_INF):
    for widget in SBUS_f_INF.winfo_children():
        widget.destroy()

    SBUS_f_INF.columnconfigure(0, weight=1)
    SBUS_f_INF.columnconfigure(3, weight=1)

    sliders = []
    for i in range(8):
        SBUS_f_INF.rowconfigure(i, weight=1)
        row_pad = (100, 0) if i == 0 else 0

        lbl = ttk.Label(SBUS_f_INF, text=f"C{i+1}", bootstyle=PRIMARY)
        lbl.grid(row=i, column=1, padx=(20, 10), pady=row_pad, sticky="e")

        c = ttk.Scale(SBUS_f_INF, from_=1000, to=2000, bootstyle=PRIMARY, length=800)
        c.set(1500)
        c.grid(row=i, column=2, padx=10, pady=row_pad, sticky="w")
        sliders.append(c)
    
    return sliders



# Main window buttons
b1 = ttk.Button(main, text="Lidar Test", bootstyle=PRIMARY, width=30, command=lidar)
b1.pack(expand=TRUE, pady=(75,0))
b2 = ttk.Button(main, text="Magnetometer Test", bootstyle=PRIMARY, width=30, command=mag) 
b2.pack(expand=TRUE)
b3 = ttk.Button(main, text="Rear Switch Plate Test", bootstyle=PRIMARY, width=30, command=switch_plate)
b3.pack(expand=TRUE)
b4 = ttk.Button(main, text="Arm Loom Test", bootstyle=PRIMARY, width=30, command=arm)
b4.pack(expand=TRUE) 
b5 = ttk.Button(main, text="Body Test", bootstyle=PRIMARY, width=30, command=body)
b5.pack(expand=TRUE) 
b6 = ttk.Button(main, text="Voltage Test", bootstyle=PRIMARY, width=30, command=volt)
b6.pack(expand=TRUE) 


home_b = ttk.Button(root, text="Home", bootstyle=OUTLINE, command=home, width=10)
home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)


# Body buttons
eth1 = ttk.Button(body_f, text="Ethernet Test", bootstyle=SECONDARY, width=20, command=Eth)
eth1.pack(expand=TRUE, anchor=E, padx=75)
SB1 = ttk.Button(body_f, text="Infravision SBUS (15-pin)", bootstyle=SECONDARY, width=20, command=SBUS_INF)
SB1.pack(expand=TRUE, anchor=E, padx=75)
SB2 = ttk.Button(body_f, text="Standard SBUS (9-pin)", bootstyle=SECONDARY, width=20)
SB2.pack(expand=TRUE, anchor=E, padx=75)
Debug = ttk.Button(body_f, text="Debug Mode", bootstyle=SECONDARY, width=20)
Debug.pack(expand=TRUE, anchor=E, padx=75)

# Arm test buttons -
test_b = ttk.Button(arm_f, text="Test", bootstyle=SECONDARY, width=10)
test_b.pack(expand=TRUE, anchor=SE, padx=50, pady=75)



# Initialize main loop for UI
main.pack(fill=BOTH, expand=True)             
root.mainloop()
