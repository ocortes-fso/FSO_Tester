import ttkbootstrap as ttk 
from ttkbootstrap.constants import *
import sys
import os
import numpy as np
from tkinter import BOTH, TRUE
import threading
import time

# must have this since not in same directory as subcodes
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# import of codes used in GUI
from Subcodes import Magnetometer, Lidar, Network_test, Arm_loom_test, Rear_switch_plate_test

mag_after_id = None
lidar_after_id = None

root = ttk.Window(themename="cyborg", size=[1280, 720], title="FSO Tester") 
style = ttk.Style()
style.configure('primary.TButton', font=(None, 24, 'bold'))
style.configure('Outline.TButton', font=(None, 14, 'bold'))
style.configure('primary.TLabel', font=(None, 24, 'bold'))
style.configure('secondary.TButton', font=(None, 20, 'bold'))
style.configure('secondary.TLabel', font=(None, 18, 'bold'))
style.configure('Header.TLabel', font=(None, 20, 'bold'))
style.configure('Sub.TLabel', font=(None, 16))

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

# labels mag
l1 = ttk.Label(mag_f, text="Waiting for Magnetometer...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l1.pack(fill=BOTH, expand=TRUE)

# labels lidar
l2 = ttk.Label(lidar_f, text="Waiting for Lidar...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l2.pack(fill=BOTH, expand=TRUE)

# labels ethernet
l3 = ttk.Label(Eth_f, text="Pinging air unit...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER) 
l3.pack(fill=BOTH, expand=TRUE)

body_left_container = ttk.Frame(body_f)
body_left_container.pack(side=LEFT, fill=BOTH, expand=TRUE)

# labels body test
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
l8.pack(pady=(10, 3))
l9 = ttk.Label(volt_container, text="A1:", bootstyle=SECONDARY, style='Sub.TLabel')
l9.pack()
l10 = ttk.Label(volt_container, text="A2:", bootstyle=SECONDARY, style='Sub.TLabel')
l10.pack()
l11 = ttk.Label(volt_container, text="A3:", bootstyle=SECONDARY, style='Sub.TLabel')
l11.pack()
l12 = ttk.Label(volt_container, text="A4:", bootstyle=SECONDARY, style='Sub.TLabel')
l12.pack()
l13 = ttk.Label(volt_container, text="4. CAN/SBUS", bootstyle=SECONDARY, style='Header.TLabel')
l13.pack(pady=(10, 3))
l14 = ttk.Label(volt_container, text="A5:", bootstyle=SECONDARY, style='Sub.TLabel')
l14.pack()
l15 = ttk.Label(volt_container, text="A6:", bootstyle=SECONDARY, style='Sub.TLabel')
l15.pack()
l16 = ttk.Label(volt_container, text="5. RC-OUT", bootstyle=SECONDARY, style='Header.TLabel')
l16.pack(pady=(10, 3))
l17 = ttk.Label(volt_container, text="A7:", bootstyle=SECONDARY, style='Sub.TLabel')
l17.pack()
l18 = ttk.Label(volt_container, text="A8:", bootstyle=SECONDARY, style='Sub.TLabel')
l18.pack()
l19 = ttk.Label(volt_container, text="6. PAYLOAD", bootstyle=SECONDARY, style='Header.TLabel')
l19.pack(pady=(10, 3))
l22 = ttk.Label(volt_container, text="A9:", bootstyle=SECONDARY, style='Sub.TLabel')
l22.pack()

# labels switch plate
l_sw = ttk.Label(switch_plate_f, text="Plug in Switch Plate to test...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l_sw.pack(fill=BOTH, expand=TRUE)

# --- SCREENS ---

def home():
    global mag_after_id, lidar_after_id
    if mag_after_id is not None:
        root.after_cancel(mag_after_id)
        mag_after_id = None
    if lidar_after_id is not None:
        root.after_cancel(lidar_after_id)
        lidar_after_id = None
    Magnetometer.close()
    Lidar.close()
    Rear_switch_plate_test.close()

    for f in [lidar_f, mag_f, switch_plate_f, arm_f, body_f, volt_f, SBUS_f, SBUS_f_INF, Eth_f]:
        f.pack_forget()
    main.pack(fill=BOTH, expand=TRUE)
    
def Eth():
    body_f.pack_forget()
    volt_f.pack_forget()
    SBUS_f.pack_forget()
    SBUS_f_INF.pack_forget()
    Eth_f.pack_forget()
    main.pack(fill=BOTH, expand=TRUE)

def lidar():
    global lidar_after_id
    main.pack_forget()
    lidar_f.pack(fill=BOTH, expand=TRUE)
    root.update()
    if lidar_after_id is None:
        update_lidar()

def mag():
    global mag_after_id
    main.pack_forget()
    mag_f.pack(fill=BOTH, expand=TRUE)
    root.update()
    if mag_after_id is None:
        update_mag()

def switch_plate():
    main.pack_forget()
    switch_plate_f.pack(fill=BOTH, expand=TRUE)
    Rear_switch_plate_test.start()
   
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

##### Functions #####

def update_mag():
    global mag_after_id
    if not mag_f.winfo_viewable():
        mag_after_id = None
        return
    val = Magnetometer.read_once()
    if val:
        l1.config(text=f"X: {val[0]} \nY: {val[1]} \nZ: {val[2]} \n|B|: {val[3]:.1f}")
    else:
        l1.config(text="Waiting for Magnetometer...")
    mag_after_id = root.after(500, update_mag)

def update_lidar():
    global lidar_after_id
    if not lidar_f.winfo_viewable():
        lidar_after_id = None
        return
    distance = Lidar.read_lidar_distance()
    if distance is not None:
        l2.config(text=f"Lidar Distance: {distance} m")
    else:
        l2.config(text="Waiting for Lidar")
    lidar_after_id = root.after(500, update_lidar)

def create_sliders(parent):
    for widget in parent.winfo_children():
        widget.destroy()
    parent.columnconfigure(0, weight=1)
    parent.columnconfigure(3, weight=1)
    for i in range(8):
        parent.rowconfigure(i, weight=1)
        lbl = ttk.Label(parent, text=f"C{i+1}", bootstyle=PRIMARY)
        lbl.grid(row=i, column=1, padx=(20, 10), sticky="e")
        c = ttk.Scale(parent, from_=1000, to=2000, bootstyle=PRIMARY, length=800)
        c.set(1500)
        c.grid(row=i, column=2, padx=10, sticky="w")

def Eth():
    body_f.pack_forget()
    Eth_f.pack(fill=BOTH, expand=TRUE)
    threading.Thread(target=Eth_test, daemon=True).start()  # run in background thread

def Eth_test():
    l3.after(0, lambda: l3.config(text="Pinging air unit..."))
    result = Network_test.ping()
    if result:
        l3.after(0, lambda: l3.config(text="PASS! Network Test Passed"))
    else:
        l3.after(0, lambda: l3.config(text="Network Test Failed"))

def arm_test():
    matrix = Arm_loom_test.arm_loom()
    pass_matrix = np.array([
        [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
        [0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0],
        [0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        [0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0],
        [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],
        [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
        [0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0],
        [0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        [0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0],
        [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1]
    ])
    l21.config(font=("Courier", 18), justify=CENTER, text=f"{matrix}")  # center and monospaced font
    l20.config(text="Pass!" if np.array_equal(matrix, pass_matrix) else "Fail!",
               bootstyle=SUCCESS if np.array_equal(matrix, pass_matrix) else DANGER)

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

# Arm test page
l20 = ttk.Label(arm_f, text="Ready to test", bootstyle=PRIMARY, font=(None, 24))
l20.pack(pady=20)
l21 = ttk.Label(arm_f, text="", bootstyle=PRIMARY)
l21.pack(expand=TRUE)
ttk.Button(arm_f, text="Run Test", bootstyle=SECONDARY, width=15, command=arm_test).pack(pady=25)  # always visible

# Start
main.pack(fill=BOTH, expand=True)
root.mainloop()
