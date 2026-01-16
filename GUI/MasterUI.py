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
style.configure('secondary.TButton', font=(None, 32, 'bold'))

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
l1 = ttk.Label(mag_f, text="Waiting for Magnetometer...", bootstyle=PRIMARY, font=(None, 48), justify=CENTER, anchor=CENTER)
l1.pack(fill=BOTH, expand=TRUE)

# labels lidar
l2 = ttk.Label(lidar_f, text="Waiting for Lidar...", bootstyle=PRIMARY, font=(None, 48), justify=CENTER, anchor=CENTER)
l2.pack(fill=BOTH, expand=TRUE)

# labels ethernet
l3 = ttk.Label(vid_f, text="Waitng for camera...", bootstyle=PRIMARY, font=(None, 48), justify=CENTER, anchor=CENTER) # centred to the video frame not parent window
l3.pack(fill=BOTH, expand=TRUE)

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
b1.pack(expand=TRUE, pady=(50,0))
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


home_b = ttk.Button(root, text="Home", bootstyle=(OUTLINE), command=home, width=10)
home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)


# Body buttons
eth1 = ttk.Button(body_f, text="Ethernet Test", bootstyle=SECONDARY, width=20, command=Eth)
eth1.pack(expand=TRUE, anchor=E, padx=75)
SB1 = ttk.Button(body_f, text="Infravision SBUS (15-pin)", bootstyle=SECONDARY, width=20, command=SBUS_INF)
SB1.pack(expand=TRUE, anchor=E, padx=75)
SB2 = ttk.Button(body_f, text="Standard SBUS (9-pin)", bootstyle=SECONDARY, width=20)
SB2.pack(expand=TRUE, anchor=E, padx=75)

# Initialize main loop for UI
main.pack(fill=BOTH, expand=True)             
root.mainloop()
