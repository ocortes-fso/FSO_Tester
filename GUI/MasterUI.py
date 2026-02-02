import ttkbootstrap as ttk 
from ttkbootstrap.constants import *
import sys
import os
import numpy as np
from tkinter import BOTH, TRUE, LEFT, TOP, W, SW, E
import threading
import time

# must have this since not in same directory as subcodes
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# import of codes used in GUI
from Subcodes import Magnetometer, Lidar, Network_test, Arm_loom_test, Rear_switch_plate_test, Body_Serial_test, PWM_test, SBUS_test, Analog_port_test


# Initialize global tracking variables
mag_after_id = None
lidar_after_id = None
sliders = []


# Thread control events
eth_stop = threading.Event()
body_stop = threading.Event()
sbus_stop = threading.Event()
inf_sbus_stop = threading.Event()

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

#labels SBUS
l_sbus = ttk.Label(SBUS_f, text="Waiting for SBUS signal...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER, font=(None, 24, 'bold'))
l_sbus.pack(fill=BOTH, expand=TRUE)

# labels lidar
l2 = ttk.Label(lidar_f, text="Waiting for Lidar...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l2.pack(fill=BOTH, expand=TRUE)

# labels ethernet
l3 = ttk.Label(Eth_f, text="Pinging air unit...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER) 
l3.pack(fill=BOTH, expand=TRUE)

body_left_container = ttk.Frame(body_f)
body_left_container.pack(side=LEFT, fill=BOTH, expand=TRUE)

# header and labels labels body test
l4 = ttk.Label(body_left_container, text="SERIAL", bootstyle=SECONDARY)
l4.pack(side=TOP, anchor=W, expand=TRUE, padx=100)
ls = ttk.Label(body_left_container, text="Waiting for heatbeat", bootstyle=SECONDARY, font=(None, 14))
ls.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

l5 = ttk.Label(body_left_container, text="ANALOG PORT", bootstyle=SECONDARY)
l5.pack(side=TOP, anchor=W, expand=TRUE, padx=100)
la = ttk.Label(body_left_container, text="", bootstyle=SECONDARY, font=(None, 14))
la.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

l6 = ttk.Label(body_left_container, text="CAN", bootstyle=SECONDARY)
l6.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

l7 = ttk.Label(body_left_container, text="PWM", bootstyle=SECONDARY)
l7.pack(side=TOP, anchor=W, expand=TRUE, padx=100)
lpwm = ttk.Label(body_left_container, text="", bootstyle=SECONDARY, font=(None, 14))
lpwm.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

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
    eth_stop.set()
    body_stop.set()
    sbus_stop.set()
    inf_sbus_stop.set()
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
    eth_stop.clear()
    body_f.pack_forget()
    Eth_f.pack(fill=BOTH, expand=TRUE)
    back_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    threading.Thread(target=Eth_test, daemon=True).start()

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
    body_stop.clear()
    main.pack_forget()
    body_f.pack(fill=BOTH, expand=TRUE)
    threading.Thread(target=body_test, daemon=True).start()

def volt():
    main.pack_forget()
    volt_f.pack(fill=BOTH, expand=TRUE)

def SBUS_INF():
    import Subcodes.INF_SBUS as INF_SBUS

    
    inf_sbus_stop.clear() # Ensure the loop can start/restart
    body_f.pack_forget()
    SBUS_f_INF.pack(fill=BOTH, expand=TRUE)
    back_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)

    # Clear existing widgets
    for widget in SBUS_f_INF.winfo_children():
        widget.destroy()
    sliders.clear()

    # Create sliders and update them continuously as sticks input from h16 is moved
    SBUS_f_INF.columnconfigure(0, weight=1)
    SBUS_f_INF.columnconfigure(3, weight=1)
    for i in range(8):
        SBUS_f_INF.rowconfigure(i, weight=1)
        lbl = ttk.Label(SBUS_f_INF, text=f"C{i+1}", bootstyle=PRIMARY)
        lbl.grid(row=i, column=1, padx=(20, 10), sticky="e")
        s = ttk.Scale(SBUS_f_INF, from_=1000, to=2000, bootstyle=PRIMARY, length=800)
        s.set(1500)
        s.grid(row=i, column=2, padx=10, sticky="w")
        sliders.append(s)

    # update loop
    def update_sliders():
        while not inf_sbus_stop.is_set():
            try:
                buf = bytearray()
                # Reference the imported INF_SBUS module functions
                for _ in range(25): 
                    buf.append(INF_SBUS.read_sbus_byte())

                channels = INF_SBUS.decode_sbus_channels(buf)
                pwm_values = [INF_SBUS.sbus_to_pwm(v) for v in channels]

                for i, val in enumerate(pwm_values):
                    if i < len(sliders):
                        root.after(0, sliders[i].set, val)
            except Exception:
                for s in sliders:
                    root.after(0, s.set, 1500)
            time.sleep(0.025)  # small delay between iterations 

    threading.Thread(target=update_sliders, daemon=True).start()



def SBUS():
    sbus_stop.clear()
    body_f.pack_forget()
    SBUS_f.pack(fill=BOTH, expand=TRUE)
    back_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    threading.Thread(target=SBUS_run_test, daemon=True).start()


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
        l2.config(text="Waiting for Lidar...")
    lidar_after_id = root.after(500, update_lidar)

def Eth_test():
    l3.after(0, lambda: l3.config(text="Pinging air unit..."))
    if eth_stop.is_set():
        return
    result = Network_test.ping()
    if eth_stop.is_set():
        return
    l3.after(0, lambda: l3.config(text="PASS! Network Test Passed" if result else "Network Test Failed", bootstyle=SUCCESS if result else DANGER))

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
    
def body_test(): 
    if body_stop.is_set():
        return
    # 1. Serial test
    serial_result = Body_Serial_test.serial_test()
    if body_stop.is_set():
        return
    ls.after(0, lambda: ls.config(text="Heartbeat received - PASS" if serial_result else "No Heartbeat - FAIL", bootstyle=SUCCESS if serial_result else DANGER, font=(None, 14)))
    
    time.sleep(0.5)
    if body_stop.is_set():
        return

    #2. Analog port test
    la.after(0, lambda: la.config(text="Running Analog Port test (Rebooting)...", bootstyle=INFO, font=(None, 14)))
    
    if body_stop.is_set():
        return
    
    output = Analog_port_test.analog_port_run()
    combined_output = f"Results: A1={output[0]:.2f} V, A2={output[1]:.2f} V"

    if (1 <= output[0] <= 1.5) and (2.25 <= output[1] <= 2.75):
        la.after(0, lambda: la.config(text=f"PASS -- {combined_output}", bootstyle=SUCCESS, font=(None, 14)))
    else:
        la.after(0, lambda: la.config(text=f"FAIL -- {combined_output}", bootstyle=DANGER, font=(None, 14)))

    # 4. PWM test
    lpwm.after(0, lambda: lpwm.config(text="Running PWM test (Rebooting)...", bootstyle=INFO, font=(None, 14)))
    pwm_result = PWM_test.run_pwm_test()
    
    if body_stop.is_set():
        return
        
    status_str = "PASS" if pwm_result[1] else "FAIL"
    combined_text = f"{status_str}!  Results: {pwm_result[0]}"
    
    lpwm.after(0, lambda: lpwm.config(text=combined_text, bootstyle=SUCCESS if pwm_result[1] else DANGER, font=(None, 14)))

def SBUS_run_test():
    # Update UI to show scanning started
    l_sbus.after(0, lambda: l_sbus.config(text="Scanning for SBUS signal...", bootstyle=INFO, font=(None, 24, 'bold')))
    if sbus_stop.is_set():
        return
    result = SBUS_test.test_sbus()
    if sbus_stop.is_set():
        return
    l_sbus.after(0, lambda: l_sbus.config(text="SBUS Signal Detected - PASS" if result else "No SBUS Signal - FAIL", bootstyle=SUCCESS if result else DANGER, font=(None, 24, 'bold')))


# Single Back button (used on SBUS, INF SBUS, Ethernet, and add to debug once tested that)
back_b = ttk.Button(root, text="Back", bootstyle=OUTLINE, command=lambda: show_body_from_back(), width=10)

def show_body_from_back():
    # Signal the background loops to stop of each below
    inf_sbus_stop.set()
    sbus_stop.set()
    eth_stop.set()
    
    back_b.pack_forget()
    for f in [SBUS_f, SBUS_f_INF, Eth_f]:
        f.pack_forget()
    body_f.pack(fill=BOTH, expand=TRUE)

# Body buttons
eth1 = ttk.Button(body_f, text="Ethernet Test", bootstyle=SECONDARY, width=20, command=Eth)
eth1.pack(expand=TRUE, anchor=E, padx=75)
SB1 = ttk.Button(body_f, text="Infravision SBUS (15-pin)", bootstyle=SECONDARY, width=20, command=SBUS_INF)
SB1.pack(expand=TRUE, anchor=E, padx=75)
SB2 = ttk.Button(body_f, text="Standard SBUS (9-pin)", bootstyle=SECONDARY, width=20, command=SBUS)
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