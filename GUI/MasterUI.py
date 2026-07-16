import time
import ttkbootstrap as ttk 
from ttkbootstrap.constants import *
import sys
import os
import numpy as np
from tkinter import BOTH, TRUE
import threading

# --- GUI Setup ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Subcodes import reset, Magnetometer, Lidar, Network_test, Arm_loom_test, Rear_switch_plate_test, Body_Serial_test, PWM_test, SBUS_test, Analog_port_test, Analog, Can_test, INF_SBUS, Spin_test, LED, Precharge, Batt_monitor

mag_after_id = None
lidar_after_id = None
batt_after_id = None
pwr_after_id = None
current_state = "IDLE"
spin_label = None
spin_bar = None
spin_running = False
spin_start_time = 0
spin_duration = 0
spin_stop = threading.Event()
spin_running_lock = threading.Lock()
Spin_test.register_stop_event(spin_stop)
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

style.configure("Stop.TButton",font=(None, 20, "bold"),padding=15)

main = ttk.Frame(root) 
root.attributes('-fullscreen', True)

Lidar_f = ttk.Frame(root) 
Mag_f = ttk.Frame(root)
Switch_plate_f = ttk.Frame(root)
loom_f = ttk.Frame(root)
Body_f = ttk.Frame(root)
Volt_f = ttk.Frame(root)
SBUS_f = ttk.Frame(root)
SBUS_f_INF = ttk.Frame(root)
Eth_f = ttk.Frame(root)
Arm_f = ttk.Frame(root)

# Labels
l1 = ttk.Label(Mag_f, text="Waiting for Magnetometer...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l1.pack(fill=BOTH, expand=TRUE)

l_sbus = ttk.Label(SBUS_f, text="Waiting for SBUS signal...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER, font=(None, 24, 'bold'))
l_sbus.pack(fill=BOTH, expand=TRUE)

# INF SBUS Label (Mirroring the normal SBUS style)
l_sbus_inf = ttk.Label(SBUS_f_INF, text="Waiting for INF SBUS signal...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER, font=(None, 24, 'bold'))
l_sbus_inf.pack(fill=BOTH, expand=TRUE)

l2 = ttk.Label(Lidar_f, text="Waiting for Lidar...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l2.pack(fill=BOTH, expand=TRUE)

l3 = ttk.Label(Eth_f, text="Pinging air unit...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER) 
l3.pack(fill=BOTH, expand=TRUE)

body_left_container = ttk.Frame(Body_f)
body_left_container.pack(side=LEFT, fill=BOTH, expand=TRUE)

l4 = ttk.Label(body_left_container, text="SERIAL", bootstyle=SECONDARY)
l4.pack(side=TOP, anchor=W, expand=TRUE, padx=100)
ls = ttk.Label(body_left_container, text="Waiting for heartbeat", bootstyle=SECONDARY, font=(None, 14))
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

volt_container = ttk.Frame(Volt_f)
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

l_sw = ttk.Label(Switch_plate_f, text="Plug in Switch Plate to test...", bootstyle=PRIMARY, justify=CENTER, anchor=CENTER)
l_sw.pack(fill=BOTH, expand=TRUE)

#battery monitor container
batt_container = ttk.Frame(Arm_f)
batt_container.pack(side=RIGHT, anchor=NE, padx=15, pady=15)

#status indicator packed container
status_container = ttk.Frame(Arm_f)
status_container.pack(side=LEFT, anchor=NW, padx=15, pady=15)

lv = ttk.Label(batt_container, text="Voltage:", bootstyle=SECONDARY, style='Sub.TLabel'); lv.pack()
li = ttk.Label(batt_container, text="Current:", bootstyle=SECONDARY, style='Sub.TLabel'); li.pack()
lt = ttk.Label(batt_container, text="Temperature:", bootstyle=SECONDARY, style='Sub.TLabel'); lt.pack()

status_dot = ttk.Label(status_container, text="●", font=("Arial", 28, "bold"))
status_dot.pack(anchor="w")

status_text = ttk.Label(status_container,text="SAFE",bootstyle=SECONDARY,style='Sub.TLabel')
status_text.pack(anchor="w")


spin_label = ttk.Label(status_container, text="", bootstyle=INFO, style='Sub.TLabel')
spin_label.pack(anchor="w")

spin_bar = ttk.Progressbar(status_container,maximum=100,bootstyle=INFO,length=160)

# --- SCREENS ---

def home():
    global mag_after_id, lidar_after_id, batt_after_id, pwr_after_id
    home_b.pack_forget()
    eth_stop.set()
    body_stop.set()
    sbus_stop.set()
    INF_sbus_stop.set()
    PWR.config(text="POWER ON")
    if mag_after_id is not None:
        root.after_cancel(mag_after_id)
        mag_after_id = None
    if lidar_after_id is not None:
        root.after_cancel(lidar_after_id)
        lidar_after_id = None
    if batt_after_id is not None:
        root.after_cancel(batt_after_id)
        batt_after_id = None
    Magnetometer.close()
    Lidar.close()
    Rear_switch_plate_test.close()
    Batt_monitor.close()
    Precharge.CLOSE_FET()
    stop_spin_progress()
    if pwr_after_id is not None:
        root.after_cancel(pwr_after_id)
        pwr_after_id = None

    for f in [Lidar_f, Mag_f, Switch_plate_f, loom_f, Body_f, Volt_f, SBUS_f, SBUS_f_INF, Eth_f, Arm_f]:
        f.pack_forget()
    main.pack(fill=BOTH, expand=TRUE)
    root.update()

def arm():
    global batt_after_id
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    Arm_f.pack(fill=BOTH, expand=TRUE)
    Precharge.INITIALIZE_SYSTEM()
    set_arm_state("IDLE")
    root.update()
    root.after(100, start_batt_monitor)

def start_batt_monitor():
    global batt_after_id
    if batt_after_id is None:
        update_batt()

def lidar():
    global lidar_after_id
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    Lidar_f.pack(fill=BOTH, expand=TRUE)
    root.update()
    if lidar_after_id is None:
        update_lidar()

def mag():
    global mag_after_id
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    Mag_f.pack(fill=BOTH, expand=TRUE)
    root.update()
    if mag_after_id is None:
        update_mag()

def switch_plate():
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    Switch_plate_f.pack(fill=BOTH, expand=TRUE)
    Rear_switch_plate_test.start()
   
def loom():
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    loom_f.pack(fill=BOTH, expand=TRUE)
    
def body():
    body_stop.clear()
    ls.config(text="Waiting for heartbeat", bootstyle=SECONDARY,font=(None, 14))
    la.config(text="", bootstyle=SECONDARY)
    lcan.config(text="", bootstyle=SECONDARY)
    lpwm.config(text="", bootstyle=SECONDARY)
    main.pack_forget()
    back_b.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    Body_f.pack(fill=BOTH, expand=TRUE)
    threading.Thread(target=body_test, daemon=True).start()

def volt():
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    Volt_f.pack(fill=BOTH, expand=TRUE)
    threading.Thread(target=ADC_test, daemon=True).start()

def SBUS_INF():
    INF_sbus_stop.clear()
    Body_f.pack_forget()
    home_b.pack_forget()
    SBUS_f_INF.pack(fill=BOTH, expand=TRUE)
    back_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    threading.Thread(target=INF_SBUS_run_test, daemon=True).start()
    
def SBUS():
    sbus_stop.clear()
    home_b.pack_forget()    
    Body_f.pack_forget()
    SBUS_f.pack(fill=BOTH, expand=TRUE)
    back_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    threading.Thread(target=SBUS_run_test, daemon=True).start()

def Eth():
    eth_stop.clear()
    Body_f.pack_forget()
    home_b.pack_forget()
    Eth_f.pack(fill=BOTH, expand=TRUE)
    back_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    threading.Thread(target=Eth_test, daemon=True).start()

# --- Functions ---

def INF_SBUS_run_test():
    l_sbus_inf.after(0, lambda: l_sbus_inf.config(text="Scanning for signal...", bootstyle=INFO, font=(None, 24, 'bold')))
    if INF_sbus_stop.is_set():
        return
    result = INF_SBUS.test_sbus() 
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
    if not Mag_f.winfo_viewable():
        mag_after_id = None
        return
    val = Magnetometer.read_once()
    if val:
        l1.config(text=f"X: {val[0]} \nY: {val[1]} \nZ: {val[2]} \n|B|: {val[3]:.1f}")
    else:
        l1.config(text="Waiting for Magnetometer...")
    mag_after_id = root.after(500, update_mag)

def set_arm_state(state):
    global current_state
    current_state = state
    
    if state == "IDLE":
        status_dot.config(foreground="white")
        status_text.config(text="SAFE")

    elif state == "PRECHARGE":
        status_dot.config(foreground="yellow")
        status_text.config(text="PRECHARGE")

    elif state == "LIVE":
        status_dot.config(foreground="green")
        status_text.config(text="LIVE")

    elif state == "FAULT":
        status_dot.config(foreground="red")
        status_text.config(text="FAULT")

    elif state == "SPINNING":
        status_dot.config(foreground="blue")
        status_text.config(text="SPINNING")

def PWR_ON():
    global pwr_after_id

    try:
        spin_stop.clear()
        Precharge.INITIALIZE_SYSTEM()
        Precharge.START_PRECHARGE()
        set_arm_state("PRECHARGE")

        PWR.config(text="PreCharging...")

        pwr_after_id = PWR.after(3000, PWR_CHECK)
        
    except Exception as e:
        print(f"[PWR ON ERROR] Cannot start precharge: {e}")
        set_arm_state("FAULT")
        Precharge.CLOSE_FET()
        PWR.config(text="Precharge FAIL")

def PWR_CHECK():
    global pwr_after_id
    pwr_after_id = None

    try:
        LED.INIT()
        LED.LED_OFF()
        set_arm_state("PRECHARGE")

        Precharge.OPEN_FET()
        PWR.config(text="FET ON...")
        root.update()

        time.sleep(0.2)

        v_check = Batt_monitor.read_battery_voltage()
        if v_check is None or v_check < 21.0:
            print(f"[PWR CHECK] Low or no voltage detected: {v_check}V")
            Precharge.CLOSE_FET()
            Precharge.TURN_OFF_PRECHARGE()
            set_arm_state("FAULT")
            PWR.config(text="Check Battery")
            time.sleep(5)
            PWR.config(text="POWER ON")
            set_arm_state("IDLE")
            return

        Precharge.TURN_OFF_PRECHARGE()
        Spin_test.claim_pwm_pins()
        set_arm_state("LIVE")
        PWR.config(text="PRECHARGE OK")

    except Exception as e:
        print(f"[PWR CHECK ERROR] Failure during activation: {e}")
        set_arm_state("FAULT")
        Precharge.CLOSE_FET()
        PWR.config(text="Power ERROR")

def SPIN():
    with spin_running_lock:
        if spin_stop.is_set():
            return

    if current_state != "LIVE":
        set_arm_state("FAULT")
        return

    spin_stop.clear()

    def run():
        try:
            set_arm_state("SPINNING")
            root.after(0, lambda: start_spin_progress("SPIN ALL", 18))

            Spin_test.SPIN_START()

            if spin_stop.is_set():
                Spin_test.SPIN_STOP()
                set_arm_state("IDLE")
                root.after(0, stop_spin_progress)
                return

            Spin_test.SPIN_STOP()
            set_arm_state("LIVE")
            root.after(0, stop_spin_progress)

        except:
            Spin_test.SPIN_STOP()
            set_arm_state("FAULT")
            root.after(0, stop_spin_progress)

    threading.Thread(target=run, daemon=True).start()


def TOP_SPIN():
    with spin_running_lock:
        if spin_stop.is_set():
            return

    if current_state != "LIVE":
        set_arm_state("FAULT")
        return

    spin_stop.clear()

    def run():
        try:
            set_arm_state("SPINNING")
            root.after(0, lambda: start_spin_progress("SPIN TOP", 11))

            Spin_test.SPIN_TOP()

            if spin_stop.is_set():
                Spin_test.SPIN_STOP()
                set_arm_state("IDLE")
                root.after(0, stop_spin_progress)
                return

            Spin_test.SPIN_STOP()
            set_arm_state("LIVE")
            root.after(0, stop_spin_progress)

        except:
            Spin_test.SPIN_STOP()
            set_arm_state("FAULT")
            root.after(0, stop_spin_progress)

    threading.Thread(target=run, daemon=True).start()


def BOT_SPIN():
    with spin_running_lock:
        if spin_stop.is_set():
            return
    if current_state != "LIVE":
        set_arm_state("FAULT")
        return

    spin_stop.clear()

    def run():
        try:
            set_arm_state("SPINNING")
            root.after(0, lambda: start_spin_progress("SPIN BOT", 11))

            Spin_test.SPIN_BOT()

            if spin_stop.is_set():
                Spin_test.SPIN_STOP()
                set_arm_state("IDLE")
                root.after(0, stop_spin_progress)
                return

            Spin_test.SPIN_STOP()
            set_arm_state("LIVE")
            root.after(0, stop_spin_progress)

        except:
            Spin_test.SPIN_STOP()
            set_arm_state("FAULT")
            root.after(0, stop_spin_progress)

    threading.Thread(target=run, daemon=True).start()


def PROP_SPIN():
    with spin_running_lock:
        if spin_stop.is_set():
            return

    if current_state != "LIVE":
        set_arm_state("FAULT")
        return

    spin_stop.clear()

    def run():
        try:
            set_arm_state("SPINNING")
            root.after(0, lambda: start_spin_progress("PROP TEST", 64))

            Spin_test.SPIN_PROP()

            if spin_stop.is_set():
                Spin_test.SPIN_STOP()
                set_arm_state("IDLE")
                root.after(0, stop_spin_progress)
                return

            Spin_test.SPIN_STOP()
            set_arm_state("LIVE")
            root.after(0, stop_spin_progress)

        except:
            Spin_test.SPIN_STOP()
            set_arm_state("FAULT")
            root.after(0, stop_spin_progress)

    threading.Thread(target=run, daemon=True).start()
    
def start_spin_progress(name, duration):
    global spin_running, spin_start_time, spin_duration
    spin_running = True
    spin_start_time = time.time()
    spin_duration = duration

    spin_label.config(text=f"Running: {name}")
    spin_bar["value"] = 0
    spin_bar.pack(anchor="w", pady=(5, 0))
    update_spin_progress()

def update_spin_progress():
    global spin_running
    if not spin_running:
        return

    elapsed = time.time() - spin_start_time
    percent = min((elapsed / spin_duration) * 100, 100)
    spin_bar["value"] = percent

    if percent < 100:
        root.after(100, update_spin_progress)
    else:
        spin_label.config(text="Completed")
        root.after(800, stop_spin_progress)

def stop_spin_progress():
    global spin_running
    spin_running = False
    spin_bar.pack_forget()
    spin_label.config(text="")

def TOGGLE_LED():
    if LED_btn.cget("text") == "Turn LED On":
        LED.LED_ON()
        LED_btn.config(text="Turn LED Off")
    else:
        LED.LED_OFF()
        LED_btn.config(text="Turn LED On")

def power_off():
    global pwr_after_id

    spin_stop.set()
    stop_spin_progress()

    try:
        Spin_test.SPIN_STOP()
    except:
        pass

    try:
        LED.LED_OFF()
    except:
        pass

    if pwr_after_id is not None:
        root.after_cancel(pwr_after_id)
        pwr_after_id = None

    try:
        Precharge.TURN_OFF_PRECHARGE()
    except:
        pass

    time.sleep(0.25) #play with this to see if imapcts power paths at all

    try:
        Precharge.CLOSE_FET()
    except:
        pass

    set_arm_state("IDLE")
    PWR.config(text="POWER ON")

def update_batt():
    global batt_after_id

    if not Arm_f.winfo_viewable():
        batt_after_id = None
        return

    V = Batt_monitor.read_battery_voltage()
    I = Batt_monitor.read_battery_current()
    T = Batt_monitor.read_battery_temperature()

    if V is not None:
        lv.config(text=f"Voltage: {V:.2f} V")

    if I is not None:
        li.config(text=f"Current: {I:.2f} A")

    if T is not None:
        lt.config(text=f"Temperature: {T:.2f} C")

    batt_after_id = root.after(500, update_batt)
        

def update_lidar():
    global lidar_after_id
    if not Lidar_f.winfo_viewable():
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
        font=(None, 24, 'bold')
    ))


def loom_test():
    matrix, gui_string = Arm_loom_test.arm_loom()
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
    l21.config(font=("Courier", 22), justify=CENTER, text=gui_string)
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
    elif (output[0] == -1) or (output[1] == -1):
        la.after(0, lambda: la.config(text=f"FAIL -- COULDNT WRITE PARAMS - CHECK CFG", bootstyle=DANGER, font=(None, 14)))
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
    Body_f.pack(fill=BOTH, expand=TRUE)

# Main window buttons
b1 = ttk.Button(main, text="Lidar Test", bootstyle=PRIMARY, width=30, command=lidar); b1.pack(expand=TRUE, pady=(50,0))
b2 = ttk.Button(main, text="Magnetometer Test", bootstyle=PRIMARY, width=30, command=mag); b2.pack(expand=TRUE)
b3 = ttk.Button(main, text="Rear Switch Plate Test", bootstyle=PRIMARY, width=30, command=switch_plate); b3.pack(expand=TRUE)
b4 = ttk.Button(main, text="Loom Test", bootstyle=PRIMARY, width=30, command=loom); b4.pack(expand=TRUE) 
b5 = ttk.Button(main, text="Body Test", bootstyle=PRIMARY, width=30, command=body); b5.pack(expand=TRUE) 
b6 = ttk.Button(main, text="Voltage Test", bootstyle=PRIMARY, width=30, command=volt); b6.pack(expand=TRUE) 
b7 = ttk.Button(main, text="Arm Test", bootstyle=PRIMARY, width=30, command=arm); b7.pack(expand=TRUE, pady=(0,50)) 

home_b = ttk.Button(root, text="Home", bootstyle=OUTLINE, command=home, width=10)
back_b = ttk.Button(root, text="Back", bootstyle=OUTLINE, command=show_body_from_back, width=10)

# Body buttons
eth1 = ttk.Button(Body_f, text="Ethernet Test", bootstyle=SECONDARY, width=20, command=Eth); eth1.pack(expand=TRUE, anchor=E, padx=75)
SB1 = ttk.Button(Body_f, text="Infravision SBUS (15-pin)", bootstyle=SECONDARY, width=20, command=SBUS_INF); SB1.pack(expand=TRUE, anchor=E, padx=75)
SB2 = ttk.Button(Body_f, text="Standard SBUS (9-pin)", bootstyle=SECONDARY, width=20, command=SBUS); SB2.pack(expand=TRUE, anchor=E, padx=75)
Debug = ttk.Button(Body_f, text="Debug Mode", bootstyle=SECONDARY, width=20); #Debug.pack(expand=TRUE, anchor=E, padx=75)   #hidden for now until we work this out

# Arm buttons
PWR = ttk.Button(Arm_f, text="POWER ON", bootstyle=PRIMARY, width=24, command=PWR_ON)
PWR.pack(expand=TRUE, pady=(25, 15))
SPIN_ALL = ttk.Button(Arm_f, text="Spin ALL", bootstyle=SECONDARY, width=24, command=SPIN)
SPIN_ALL.pack(expand=TRUE, pady=5)
SPIN_TOP = ttk.Button(Arm_f, text="Spin TOP", bootstyle=SECONDARY, width=24, command=TOP_SPIN)
SPIN_TOP.pack(expand=TRUE, pady=5)
SPIN_BOT = ttk.Button(Arm_f, text="Spin BOT", bootstyle=SECONDARY, width=24, command=BOT_SPIN)
SPIN_BOT.pack(expand=TRUE, pady=5)
LED_btn = ttk.Button(Arm_f, text="Turn LED On", bootstyle=SECONDARY, width=24, command=TOGGLE_LED)
LED_btn.pack(expand=TRUE, pady=5)
PROP = ttk.Button(Arm_f, text="Prop Test", bootstyle=SECONDARY, width=24, command=PROP_SPIN)
PROP.pack(expand=TRUE, pady=(5, 15))
STOP_btn = ttk.Button(Arm_f,text="POWER OFF",style="Stop.TButton",command=power_off)
STOP_btn.pack(expand=TRUE, pady=(15, 25))


# Loom test page
l20 = ttk.Label(loom_f, text="Ready to test", bootstyle=PRIMARY, font=(None, 24)); l20.pack(pady=20)
l21 = ttk.Label(loom_f, text="", bootstyle=PRIMARY); l21.pack(expand=TRUE)
ttk.Button(loom_f, text="Run Test", bootstyle=SECONDARY, width=15, command=loom_test).pack(pady=25)

main.pack(fill=BOTH, expand=True)
root.mainloop()