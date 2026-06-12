import time
import lgpio
import ttkbootstrap as ttk 
from ttkbootstrap.constants import *
import sys
import os
import numpy as np
from tkinter import BOTH, TRUE
import threading

# --- SBUS INF Logic ---
def test_sbus():
    SBUS_GPIO = 14
    SBUS_CHIP = 4
    BIT_TIME_US = 10
    SBUS_FRAME_LENGTH = 25
    SBUS_HEADER = 0x0F

    h = lgpio.gpiochip_open(SBUS_CHIP)
    lgpio.gpio_claim_input(h, SBUS_GPIO)

    def read_sbus_byte():
        t_wait = time.time()
        while lgpio.gpio_read(h, SBUS_GPIO) == 1:
            if time.time() - t_wait > 0.5: 
                return None
        
        time.sleep(1.5 * BIT_TIME_US / 1_000_000)
        
        value = 0
        for i in range(8):
            bit = lgpio.gpio_read(h, SBUS_GPIO)
            value |= (bit << i)
            time.sleep(BIT_TIME_US / 1_000_000)
        
        return value ^ 0xFF

    _sbus_read = False
    t0 = time.time()
    
    while time.time() - t0 < 5:  
        byte = read_sbus_byte()
        if byte == SBUS_HEADER:
            _sbus_read = True
            break 
        
    lgpio.gpiochip_close(h)
    return _sbus_read

# --- GUI Setup ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import reset, Magnetometer, Lidar, Network_test, Arm_loom_test, Rear_switch_plate_test, Body_Serial_test, PWM_test, SBUS_test, Analog_port_test, Analog, Can_test, INF_SBUS

mag_after_id = None
lidar_after_id = None

eth_stop = threading.Event()
body_stop = threading.Event()
sbus_stop = threading.Event()
INF_sbus_stop = threading.Event()

root = ttk.Window(themename="cyborg", size=[1280, 720], title="FSO Tester") 
style = ttk.Style()
style.configure('primary.TButton', font=(None, 24, 'bold'))
style.configure('Outline.TButton', font=(None, 14, 'bold'))
style.configure('primary.TLabel', font=(None, 24, 'bold'))
style.configure('secondary.TButton', font=(None, 20, 'bold'))
style.configure('secondary.TLabel', font=(None, 18, 'bold'))
style.configure('Header.TLabel', font=(None, 20, 'bold'))
style.configure('Sub.TLabel', font=(None, 18))

main = ttk.Frame(root) 
root.attributes('-fullscreen', True)

lidar_f = ttk.Frame(root) 
mag_f = ttk.Frame(root)
switch_plate_f = ttk.Frame(root)
arm_f = ttk.Frame(root)
body_f = ttk.Frame(root)
volt_f = ttk.Frame(root)
SBUS_f = ttk.Frame(root)
SBUS_f_INF = ttk.Frame(root)
Eth_f = ttk.Frame(root)

# Labels
l1 = ttk.Label(mag_f, text="Waiting for Magnetometer...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l1.pack(fill=BOTH, expand=TRUE)

l_sbus = ttk.Label(SBUS_f, text="Waiting for SBUS signal...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER, font=(None, 24, 'bold'))
l_sbus.pack(fill=BOTH, expand=TRUE)

# INF SBUS Label (Mirroring the normal SBUS style)
l_sbus_inf = ttk.Label(SBUS_f_INF, text="Waiting for INF SBUS signal...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER, font=(None, 24, 'bold'))
l_sbus_inf.pack(fill=BOTH, expand=TRUE)

l2 = ttk.Label(lidar_f, text="Waiting for Lidar...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l2.pack(fill=BOTH, expand=TRUE)

l3 = ttk.Label(Eth_f, text="Pinging air unit...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER) 
l3.pack(fill=BOTH, expand=TRUE)

body_left_container = ttk.Frame(body_f)
body_left_container.pack(side=LEFT, fill=BOTH, expand=TRUE)

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
lcan = ttk.Label(body_left_container, text="", bootstyle=SECONDARY, font=(None, 14))
lcan.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

l7 = ttk.Label(body_left_container, text="PWM", bootstyle=SECONDARY)
l7.pack(side=TOP, anchor=W, expand=TRUE, padx=100)
lpwm = ttk.Label(body_left_container, text="", bootstyle=SECONDARY, font=(None, 14))
lpwm.pack(side=TOP, anchor=W, expand=TRUE, padx=100)

volt_container = ttk.Frame(volt_f)
volt_container.pack(expand=TRUE)

l8 = ttk.Label(volt_container, text="3. SERIAL", bootstyle=SECONDARY, style='Header.TLabel')
l8.pack(pady=(10, 3))
l9 = ttk.Label(volt_container, text="V1:", bootstyle=SECONDARY, style='Sub.TLabel'); l9.pack()
l10 = ttk.Label(volt_container, text="V2:", bootstyle=SECONDARY, style='Sub.TLabel'); l10.pack()
l11 = ttk.Label(volt_container, text="V3:", bootstyle=SECONDARY, style='Sub.TLabel'); l11.pack()
l12 = ttk.Label(volt_container, text="V4:", bootstyle=SECONDARY, style='Sub.TLabel'); l12.pack()
l13 = ttk.Label(volt_container, text="4. CAN/SBUS", bootstyle=SECONDARY, style='Header.TLabel')
l13.pack(pady=(10, 3))
l14 = ttk.Label(volt_container, text="V5:", bootstyle=SECONDARY, style='Sub.TLabel'); l14.pack()
l15 = ttk.Label(volt_container, text="V6:", bootstyle=SECONDARY, style='Sub.TLabel'); l15.pack()
l16 = ttk.Label(volt_container, text="5. RC-OUT", bootstyle=SECONDARY, style='Header.TLabel')
l16.pack(pady=(10, 3))
l17 = ttk.Label(volt_container, text="V7:", bootstyle=SECONDARY, style='Sub.TLabel'); l17.pack()
l18 = ttk.Label(volt_container, text="V8:", bootstyle=SECONDARY, style='Sub.TLabel'); l18.pack()
l19 = ttk.Label(volt_container, text="6. PAYLOAD", bootstyle=SECONDARY, style='Header.TLabel')
l19.pack(pady=(10, 3))
l22 = ttk.Label(volt_container, text="V9:", bootstyle=SECONDARY, style='Sub.TLabel'); l22.pack()

l_sw = ttk.Label(switch_plate_f, text="Plug in Switch Plate to test...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l_sw.pack(fill=BOTH, expand=TRUE)

# --- SCREENS ---

def home():
    global mag_after_id, lidar_after_id
    home_b.pack_forget()
    eth_stop.set()
    body_stop.set()
    sbus_stop.set()
    INF_sbus_stop.set()
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

def lidar():
    global lidar_after_id
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    lidar_f.pack(fill=BOTH, expand=TRUE)
    root.update()
    if lidar_after_id is None:
        update_lidar()

def mag():
    global mag_after_id
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    mag_f.pack(fill=BOTH, expand=TRUE)
    root.update()
    if mag_after_id is None:
        update_mag()

def switch_plate():
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    switch_plate_f.pack(fill=BOTH, expand=TRUE)
    Rear_switch_plate_test.start()
   
def arm():
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    arm_f.pack(fill=BOTH, expand=TRUE)
    
def body():
    body_stop.clear()
    main.pack_forget()
    back_b.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    body_f.pack(fill=BOTH, expand=TRUE)
    threading.Thread(target=body_test, daemon=True).start()

def volt():
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    volt_f.pack(fill=BOTH, expand=TRUE)
    threading.Thread(target=ADC_test, daemon=True).start()

def SBUS_INF():
    INF_sbus_stop.clear()
    body_f.pack_forget()
    home_b.pack_forget()
    SBUS_f_INF.pack(fill=BOTH, expand=TRUE)
    back_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    threading.Thread(target=INF_SBUS_run_test, daemon=True).start()
    
def SBUS():
    sbus_stop.clear()
    home_b.pack_forget()    
    body_f.pack_forget()
    SBUS_f.pack(fill=BOTH, expand=TRUE)
    back_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    threading.Thread(target=SBUS_run_test, daemon=True).start()

def Eth():
    eth_stop.clear()
    body_f.pack_forget()
    home_b.pack_forget()
    Eth_f.pack(fill=BOTH, expand=TRUE)
    back_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    threading.Thread(target=Eth_test, daemon=True).start()

# --- Functions ---

def INF_SBUS_run_test():
    l_sbus_inf.after(0, lambda: l_sbus_inf.config(text="Scanning for signal...", bootstyle=INFO, font=(None, 24, 'bold')))
    if INF_sbus_stop.is_set():
        return
    result = test_sbus() # Using the local test_sbus code provided
    if INF_sbus_stop.is_set():
        return
    l_sbus_inf.after(0, lambda: l_sbus_inf.config(
        text="INF SBUS Signal Detected - PASS" if result else "No INF SBUS Signal - FAIL", 
        bootstyle=SUCCESS if result else DANGER, 
        font=(None, 24, 'bold')))

def SBUS_run_test():
    l_sbus.after(0, lambda: l_sbus.config(text="Scanning for SBUS signal...", bootstyle=INFO, font=(None, 24, 'bold')))
    if sbus_stop.is_set():
        return
    result = SBUS_test.test_sbus()
    if sbus_stop.is_set():
        return
    l_sbus.after(0, lambda: l_sbus.config(text="SBUS Signal Detected - PASS" if result else "No SBUS Signal - FAIL", bootstyle=SUCCESS if result else DANGER, font=(None, 24, 'bold')))

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
    l3.after(0, lambda: l3.config(
    text="PASS! Network Test Passed" if result else "Network Test Failed", 
    bootstyle=SUCCESS if result else DANGER, 
    font=(None, 24, 'bold') if result else (None, 24, 'bold')
))

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
    l21.config(font=("Courier", 18), justify=CENTER, text=f"{matrix}")
    l20.config(text="Pass!" if np.array_equal(matrix, pass_matrix) else "Fail!",
               bootstyle=SUCCESS if np.array_equal(matrix, pass_matrix) else DANGER)
    
def body_test(): 
    if body_stop.is_set():
        return
    serial_result = Body_Serial_test.serial_test()
    if body_stop.is_set():
        return
    ls.after(0, lambda: ls.config(text="Heartbeat received - PASS" if serial_result else "No Heartbeat - FAIL", bootstyle=SUCCESS if serial_result else DANGER, font=(None, 14)))
    
    time.sleep(0.5)
    if body_stop.is_set():
        return

    la.after(0, lambda: la.config(text="Running Analog Port test (Rebooting)...", bootstyle=INFO, font=(None, 14)))
    output = Analog_port_test.analog_port_run()
    if body_stop.is_set():
        return
    
    combined_output = f"Results: A1={output[0]:.2f} V, A2={output[1]:.2f} V"
    if (0.7 <= output[0] <= 0.9) and (1.5 <= output[1] <= 1.7):
        la.after(0, lambda: la.config(text=f"PASS -- {combined_output}", bootstyle=SUCCESS, font=(None, 14)))
    if (output[0] == -1) or (output[1] == -1):
        la.after(0, lambda: la.config(text=f"FAIL -- COULDNT WRITE PARMS - CHECK CFG", bootstyle=SUCCESS, font=(None, 14)))
    else:
        la.after(0, lambda: la.config(text=f"FAIL -- {combined_output}", bootstyle=DANGER, font=(None, 14)))

    if body_stop.is_set():
        return
    lcan.after(0, lambda: lcan.config(text="Running CAN test ...", bootstyle=INFO, font=(None, 14)))
    Can_status = Can_test.run_can()
    if Can_status == True:
        lcan.after(0, lambda: lcan.config(text="CAN Test PASS!", bootstyle=SUCCESS, font=(None, 14)))
    elif Can_status == False:
        lcan.after(0, lambda: lcan.config(text="CAN Test FAIL!", bootstyle=DANGER, font=(None, 14)))
    else:
        lcan.after(0, lambda: lcan.config(text="CAN Test ERROR!", bootstyle=DANGER, font=(None, 14)))
    
    lpwm.after(0, lambda: lpwm.config(text="Running PWM test (Rebooting)...", bootstyle=INFO, font=(None, 14)))
    pwm_result = PWM_test.run_pwm_test()
    if body_stop.is_set():
        return
    status_str = "PASS" if pwm_result[1] else "FAIL"
    combined_text = f"{status_str}!  Results: {pwm_result[0]}"
    lpwm.after(0, lambda: lpwm.config(text=combined_text, bootstyle=SUCCESS if pwm_result[1] else DANGER, font=(None, 14)))

    reset.run_reset()

def ADC_test():
    labels_map = {
        "STD SERIAL-12V": l9, "STD SERIAL-5V":  l10,
        "IV SERIAL-12V":  l11, "IV SERIAL-5V":  l12,
        "CAN/SBUS-12V":   l14, "CAN/SBUS-5V":   l15,
        "RC OUT-12V":     l17, "RC OUT-5V":      l18,
        "PAYLOAD":        l22,
    }
    for name, w in labels_map.items():
        w.after(0, lambda w=w, name=name: w.config(text=f"{name}: Reading...", bootstyle=INFO, font=('none', 18)))
    
    try:
        results = Analog.read_all_channels(timeout = 1.0)
    except Exception as e:
        for name, w in labels_map.items():
            w.after(0, lambda w=w, name=name: w.config(text=f"{name}: ERR -> FAIL", bootstyle=DANGER))
        return
        
    for r in results:
        label = r["label"]
        value = r["value"]
        ok    = r["pass"]
        if label in labels_map:
            w = labels_map[label]
            status = "PASS" if ok else "FAIL"
            boot = SUCCESS if ok else DANGER
            w.after(0, lambda w=w, label=label, value=value, status=status, boot=boot:
                    w.config(text=f"{label}: {value:.2f} V --> {status}", bootstyle=boot))

# --- Navigation ---
def show_body_from_back():
    back_b.pack_forget()
    for f in [SBUS_f, SBUS_f_INF, Eth_f]:
        f.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    body_f.pack(fill=BOTH, expand=TRUE)

# Main window buttons
b1 = ttk.Button(main, text="Lidar Test", bootstyle=PRIMARY, width=30, command=lidar); b1.pack(expand=TRUE, pady=(75,0))
b2 = ttk.Button(main, text="Magnetometer Test", bootstyle=PRIMARY, width=30, command=mag); b2.pack(expand=TRUE)
b3 = ttk.Button(main, text="Rear Switch Plate Test", bootstyle=PRIMARY, width=30, command=switch_plate); b3.pack(expand=TRUE)
b4 = ttk.Button(main, text="Arm Loom Test", bootstyle=PRIMARY, width=30, command=arm); b4.pack(expand=TRUE) 
b5 = ttk.Button(main, text="Body Test", bootstyle=PRIMARY, width=30, command=body); b5.pack(expand=TRUE) 
b6 = ttk.Button(main, text="Voltage Test", bootstyle=PRIMARY, width=30, command=volt); b6.pack(expand=TRUE, pady=(0,75)) 

home_b = ttk.Button(root, text="Home", bootstyle=OUTLINE, command=home, width=10)
back_b = ttk.Button(root, text="Back", bootstyle=OUTLINE, command=show_body_from_back, width=10)

# Body buttons
eth1 = ttk.Button(body_f, text="Ethernet Test", bootstyle=SECONDARY, width=20, command=Eth); eth1.pack(expand=TRUE, anchor=E, padx=75)
SB1 = ttk.Button(body_f, text="Infravision SBUS (15-pin)", bootstyle=SECONDARY, width=20, command=SBUS_INF); SB1.pack(expand=TRUE, anchor=E, padx=75)
SB2 = ttk.Button(body_f, text="Standard SBUS (9-pin)", bootstyle=SECONDARY, width=20, command=SBUS); SB2.pack(expand=TRUE, anchor=E, padx=75)
Debug = ttk.Button(body_f, text="Debug Mode", bootstyle=SECONDARY, width=20); Debug.pack(expand=TRUE, anchor=E, padx=75)

# Arm test page
l20 = ttk.Label(arm_f, text="Ready to test", bootstyle=PRIMARY, font=(None, 24)); l20.pack(pady=20)
l21 = ttk.Label(arm_f, text="", bootstyle=PRIMARY); l21.pack(expand=TRUE)
ttk.Button(arm_f, text="Run Test", bootstyle=SECONDARY, width=15, command=arm_test).pack(pady=25)

main.pack(fill=BOTH, expand=True)
root.mainloop()
