import time
import ttkbootstrap as ttk 
from ttkbootstrap.constants import *
import sys
import os
import numpy as np
from tkinter import BOTH, TRUE
import threading
import queue                    #####*****CHANGES*****##### worker -> Tk thread handoff

# --- GUI Setup ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
#####*****CHANGES*****#####
# Hobbywing_Prop_Test added for the new "Prop TEST V2" page.
from Subcodes import reset, Magnetometer, Lidar, Network_test, Arm_loom_test, Rear_switch_plate_test, Body_Serial_test, PWM_test, SBUS_test, Analog_port_test, Analog, Can_test, INF_SBUS, Spin_test, LED, Precharge, Batt_monitor, Hobbywing_Prop_Test
#####*****END CHANGES*****#####

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
arm_powered = False

#####*****CHANGES*****#####
# --- Prop TEST V2 page state ---
# Its own stop Event, kept separate from spin_stop so cancelling a V2 phase
# cannot interfere with the old Arm Test page (and vice versa).
propv2_stop = threading.Event()
Hobbywing_Prop_Test.register_stop_event(propv2_stop)

propv2_after_id = None          # handle for the label refresh loop
propv2_state = "NO POWER"
propv2_running = False          # True while a phase worker thread is alive
propv2_fault_latched = False    # so an auto-abort is only acted on once
propv2_bar_running = False
propv2_bar_start = 0
propv2_bar_duration = 1

# While True, the refresh loop owns the status corner and derives SAFE / FAULT
# from the live bus reading. Switched off whenever a handler owns the state
# instead (precharging, running, or latched fault), so the loop cannot paint
# over it at 10 Hz.
propv2_idle_watch = False
propv2_idle_note = ""           # extra context for the idle line, e.g. why we stopped

# Worker threads post UI updates here instead of calling root.after(0, ...).
# Tkinter is not thread-safe: touching it from a worker can raise
# "main thread is not in main loop". update_propv2() already runs on the Tk
# thread at 10 Hz, so it drains this queue and applies the updates there.
propv2_ui_queue = queue.Queue()

# --- Body test navigation lock ---
# The body test reboots the flight controller twice (analog port, then PWM).
# Walking away mid-reboot leaves the FC half-configured, so navigation is
# locked until the PWM test returns.
body_nav_locked = False
body_pwm_done = threading.Event()   # set by body_test() the moment run_pwm_test() returns
body_lock_start = 0
# Set by body_test when a run stops early, rendered once the lock lifts.
body_result_note = ""
# The running worker, so Start can refuse to launch a second one.
body_thread = None

# Hard ceiling on the lock, because two of the four sections can block forever:
# Analog_port_test and PWM_test both call master.wait_heartbeat() with no
# timeout, so a flight controller that never answers hangs the worker thread and
# body_pwm_done is never set. A healthy full run is about 55 s (20 s settle in
# the analog port test, 15 s in the PWM test, plus the param writes), so 180 s
# is roughly 3x headroom and still bounded - the operator always gets back out.
BODY_LOCK_MAX_S = 180
#####*****END CHANGES*****#####


root = ttk.Window(themename="cyborg", size=[1280, 720], title="FSO Tester") 
style = ttk.Style()
style.configure('primary.TButton', font=(None, 24, 'bold'))
style.configure('Outline.TButton', font=(None, 14, 'bold'))
style.configure('primary.TLabel', font=(None, 24, 'bold'))
style.configure('secondary.TButton', font=(None, 20, 'bold'))
style.configure('secondary.TLabel', font=(None, 18, 'bold'))
style.configure('Header.TLabel', font=(None, 20, 'bold'))
style.configure('Sub.TLabel', font=(None, 18))

style.configure("Arm.TButton", font=(None, 20, "bold"), padding=10, background="#0d6efd", foreground="white")
style.configure("ArmDanger.TButton", font=(None, 20, "bold"), padding=10, background="#dc3545", foreground="white")
style.configure("ArmSuccess.TButton", font=(None, 20, "bold"), padding=10, background="#198754", foreground="white")
style.configure("Stop.TButton", font=(None, 20, "bold"), padding=10, background="#dc3545", foreground="white")

#####*****CHANGES*****#####
# Deliberately the loudest thing on the Prop TEST V2 page: bigger font and far
# more padding than any other button, so it is the one you hit without looking.
style.configure("EStop.TButton", font=(None, 28, "bold"), padding=22, background="#b02a37", foreground="white")
style.configure("PropIdle.TButton", font=(None, 18, "bold"), padding=8, background="#0d6efd", foreground="white")
style.configure("PropBusy.TButton", font=(None, 18, "bold"), padding=8, background="#fd7e14", foreground="white")
style.configure("PropOn.TButton", font=(None, 18, "bold"), padding=8, background="#198754", foreground="white")
#####*****END CHANGES*****#####


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
PropV2_f = ttk.Frame(root)      #####*****CHANGES*****##### Prop TEST V2 page

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

#####*****CHANGES*****#####
# Explains why Home and the sub-test buttons are greyed out while the body
# test is running. Always packed, just empty when there is nothing to say.
lbody_lock = ttk.Label(body_left_container, text="", bootstyle=SECONDARY, font=(None, 13, "italic"))
lbody_lock.pack(side=TOP, anchor=W, expand=TRUE, padx=100)
#####*****END CHANGES*****#####

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

lpwm_status = ttk.Label(
    batt_container,
    text="PWM1: --   PWM2: --",
    bootstyle=SECONDARY,
    style='Sub.TLabel'
)
lpwm_status.pack(pady=(10,0))





status_dot = ttk.Label(status_container, text="●", font=("Arial", 28, "bold"))
status_dot.pack(anchor="w")

status_text = ttk.Label(status_container,text="SAFE",bootstyle=SECONDARY,style='Sub.TLabel')
status_text.pack(anchor="w")


spin_label = ttk.Label(status_container, text="", bootstyle=INFO, style='Sub.TLabel')
spin_label.pack(anchor="w")

spin_bar = ttk.Progressbar(status_container,maximum=100,bootstyle=INFO,length=160)

#####*****CHANGES*****#####
# --------------------------------------------------------------------------
# Prop TEST V2 page - layout
# --------------------------------------------------------------------------
# Same arrangement the Arm Test page uses: the status/telemetry column is
# packed first with side=RIGHT so it owns the top-right corner, and the button
# column then takes whatever width is left.
#
# Only the labels are created here. The buttons are created further down with
# the rest of the page buttons, because `command=` is evaluated immediately and
# the handler functions do not exist yet at this point in the file.

propv2_side = ttk.Frame(PropV2_f)
propv2_side.pack(side=RIGHT, anchor=NE, padx=25, pady=20)

propv2_dot = ttk.Label(propv2_side, text="●", font=("Arial", 34, "bold"), foreground="white")
propv2_dot.pack(anchor="e")

propv2_state_lbl = ttk.Label(propv2_side, text="NO POWER", bootstyle=SECONDARY, font=(None, 22, "bold"))
propv2_state_lbl.pack(anchor="e")

# Second line of the status: which phase/step, or why we faulted.
propv2_detail_lbl = ttk.Label(propv2_side, text="press Start Precharge", bootstyle=INFO, font=(None, 13))
propv2_detail_lbl.pack(anchor="e", pady=(0, 18))

propv2_v_lbl = ttk.Label(propv2_side, text="Voltage:  --", bootstyle=SECONDARY, style='Sub.TLabel')
propv2_v_lbl.pack(anchor="e")
propv2_i_lbl = ttk.Label(propv2_side, text="Current:  --", bootstyle=SECONDARY, style='Sub.TLabel')
propv2_i_lbl.pack(anchor="e")
propv2_w_lbl = ttk.Label(propv2_side, text="Power:    --", bootstyle=SECONDARY, style='Sub.TLabel')
propv2_w_lbl.pack(anchor="e")
propv2_t_lbl = ttk.Label(propv2_side, text="Temp:     --", bootstyle=SECONDARY, style='Sub.TLabel')
propv2_t_lbl.pack(anchor="e")

# PWM actually being transmitted, read back from the PWM layer rather than
# from whatever the GUI last asked for - so a clamp or a safety drop shows up
# here instead of being hidden.
propv2_pwm_lbl = ttk.Label(propv2_side, text="PWM TOP: off    BOT: off", bootstyle=INFO, font=(None, 17, "bold"))
propv2_pwm_lbl.pack(anchor="e", pady=(16, 0))

propv2_bar = ttk.Progressbar(propv2_side, maximum=100, bootstyle=INFO, length=220)
#####*****END CHANGES*****#####

# --- SCREENS ---

def home():
    global mag_after_id, lidar_after_id, batt_after_id, pwr_after_id
    global propv2_after_id, propv2_idle_watch                #####*****CHANGES*****#####

    #####*****CHANGES*****#####
    # Belt and braces. The button is already disabled while the body test is
    # mid-reboot, but guarding here too means no future caller can tear the
    # page down behind the lock's back.
    if body_nav_locked:
        print("[HOME] blocked: body test is mid-reboot")
        return
    #####*****END CHANGES*****#####

    home_b.pack_forget()
    eth_stop.set()

    #####*****CHANGES*****#####
    # Leaving the page must never leave the bus live. Done first, before the
    # Precharge.CLOSE_SYSTEM() further down, because the session teardown needs
    # a valid gpiochip handle to drop the throttle frames cleanly.
    propv2_stop.set()
    propv2_idle_watch = False
    if propv2_after_id is not None:
        root.after_cancel(propv2_after_id)
        propv2_after_id = None
    if Hobbywing_Prop_Test.session_live():
        # Leaving the page is a normal operator action, so power off normally
        # rather than flagging an emergency. The exception is walking out with
        # a phase still running - that abandoned a run, so keep the trace.
        if propv2_running:
            Hobbywing_Prop_Test.mark_log_keep("page left mid-phase")
        Hobbywing_Prop_Test.session_power_off()
    # Stops the sampler and closes the I2C bus. The sampler outlives the
    # emergency stop on purpose, so leaving the page is what actually ends it -
    # and it must end before the Arm Test page's own I2C polling can start.
    Hobbywing_Prop_Test.session_stop_monitor()
    propv2_bar_stop()
    #####*****END CHANGES*****#####
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
    Precharge.CLOSE_SYSTEM()
    stop_spin_progress()
    if pwr_after_id is not None:
        root.after_cancel(pwr_after_id)
        pwr_after_id = None

    #####*****CHANGES*****##### PropV2_f added to the teardown list
    for f in [Lidar_f, Mag_f, Switch_plate_f, loom_f, Body_f, Volt_f, SBUS_f, SBUS_f_INF, Eth_f, Arm_f, PropV2_f]:
        f.pack_forget()
    main.pack(fill=BOTH, expand=TRUE)
    root.update()

def arm():
    global batt_after_id
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    Arm_f.pack(fill=BOTH, expand=TRUE)
    lpwm_status.config(text="PWM1: --   PWM2: --")
    Precharge.INITIALIZE_SYSTEM()
    LED.INIT()
    LED.LED_OFF()
    Precharge.CLOSE_FET()
    set_arm_state("IDLE")
    root.update()
    root.after(100, start_batt_monitor)

def start_batt_monitor():
    global batt_after_id
    if batt_after_id is None:
        update_batt()


#####*****CHANGES*****#####
# ==========================================================================
# Body test: Start/Stop and the navigation lock
# ==========================================================================
# The body test reboots the flight controller twice: once in the analog port
# test and again in the PWM test. If the operator leaves the page mid-reboot
# the FC is left with the test parameters still written to it, so every way
# off this page is disabled from Start until the PWM test returns.
#
# The lock is taken by the Start button, not by opening the page - so the
# Ethernet and SBUS tests are reachable the moment you arrive.
#
# "Every way off" is four buttons: Home, plus the three sub-test buttons on the
# Body page itself (Ethernet / INF SBUS / Standard SBUS), which pack_forget
# Body_f and would abandon the run just as effectively as Home would.
# The main menu buttons need no handling - `main` is unpacked while this page
# is up, so they are not reachable in the first place.

def body_nav_buttons():
    return [home_b, eth1, SB1, SB2]


def body_lock_nav(locked):
    """
    Disable/enable every exit from the Body page. Tk thread only.

    Also drives Start/Stop, because "the lock is held" and "the test is
    running" are the same condition - keeping them in one place means they
    cannot drift apart.
    """
    global body_nav_locked
    body_nav_locked = locked

    for b in body_nav_buttons():
        b.config(state="disabled" if locked else "normal")

    #####*****CHANGES*****#####
    BODY_START.config(state="disabled" if locked else "normal")
    BODY_STOP.config(state="normal" if locked else "disabled")
    #####*****END CHANGES*****#####

    # Say why the buttons are dead, or the next person to use the rig will
    # reasonably assume the GUI has hung.
    if locked:
        lbody_lock.config(
            text="Test running - navigation locked until the PWM reboot completes",
            bootstyle=WARNING,
        )
    elif body_result_note:
        # The run stopped early and left an explanation. Show that rather than
        # clearing the line, which is what used to happen.
        lbody_lock.config(text=body_result_note, bootstyle=DANGER)
    else:
        lbody_lock.config(text="", bootstyle=SECONDARY)


#####*****CHANGES*****#####
def body_reset_labels():
    """Clear the four result lines plus the status note. Tk thread only."""
    ls.config(text="Waiting for heartbeat", bootstyle=SECONDARY, font=(None, 14))
    la.config(text="", bootstyle=SECONDARY)
    lcan.config(text="", bootstyle=SECONDARY)
    lpwm.config(text="", bootstyle=SECONDARY)
    lbody_lock.config(text="", bootstyle=SECONDARY)


def body_start():
    """
    Start button. Runs the four body-test sections in a worker thread.

    The navigation lock is taken here, on the Tk thread, before the thread is
    started - so the exits are already dead before the first reboot can begin.
    """
    global body_lock_start, body_result_note, body_thread

    # A run can still be finishing reset.run_reset() after the lock lifted, so
    # check the thread rather than the lock before starting a second one.
    if body_thread is not None and body_thread.is_alive():
        print("[BODY] already running")
        return

    body_result_note = ""
    body_stop.clear()
    body_pwm_done.clear()
    body_reset_labels()

    body_lock_start = time.time()
    body_lock_nav(True)

    body_thread = threading.Thread(target=body_test, daemon=True)
    body_thread.start()
    body_nav_watch(body_thread)


def body_stop_test():
    """
    Stop button. Asks the run to stop at the next section boundary.

    It cannot be instant: body_test only checks the flag between sections, and
    the sections themselves contain fixed settles that cannot be cut short (20 s
    in the analog port test, 15 s in the PWM test) because the flight controller
    is rebooting through them. So this is a request, and the label says so.

    The navigation lock deliberately stays on until the section ends - that is
    the whole point of it, the FC is still mid-reboot.
    """
    global body_result_note

    if not body_nav_locked:
        return

    print("[BODY] stop requested")
    body_stop.set()
    BODY_STOP.config(state="disabled")
    body_result_note = "Stopped by operator - results below may be incomplete."
    lbody_lock.config(
        text="Stopping - waiting for the current section to finish "
             "(a reboot cannot be cut short)...",
        bootstyle=WARNING,
    )
#####*****END CHANGES*****#####


def body_nav_watch(t):
    """
    Release the lock once the PWM test has returned.

    Polls from the Tk thread instead of having the worker call back into Tk:
    setting a threading.Event from a worker is safe, calling widget methods
    from one is not.

    Unlocks on ANY of three conditions:

      * body_pwm_done is set  -> the PWM test returned. The normal case, and
        the point the lock is actually meant to cover. Note this happens
        whether the sections PASSed or FAILed - a FAIL result does not stop the
        run, the next section still reboots the FC, so the lock has to hold
        until the last reboot is done either way.

      * the thread has died   -> body_test returned early or raised. Without
        this, a crash anywhere upstream would leave the operator with no way
        off the page.

      * BODY_LOCK_MAX_S elapsed -> the worker is hung. Analog_port_test and
        PWM_test both wait_heartbeat() with no timeout, so an unresponsive
        flight controller blocks them forever and neither of the conditions
        above would ever fire. The operator needs to get out and go fix it, so
        the lock gives up rather than trapping them in the page.
    """
    if body_pwm_done.is_set() or not t.is_alive():
        body_lock_nav(False)
        return

    if time.time() - body_lock_start > BODY_LOCK_MAX_S:
        print(f"[BODY] nav lock released after {BODY_LOCK_MAX_S}s - "
              f"a test section is not returning")
        body_lock_nav(False)
        lbody_lock.config(
            text=f"Unlocked after {BODY_LOCK_MAX_S}s - a section is still "
                 f"running or hung. Results above may be incomplete.",
            bootstyle=DANGER,
        )
        return

    root.after(300, lambda: body_nav_watch(t))
#####*****END CHANGES*****#####


#####*****CHANGES*****#####
# ==========================================================================
# Prop TEST V2 page - behaviour
# ==========================================================================
#
# Division of labour, which is the thing worth understanding here:
#
#   * Hobbywing_Prop_Test owns the hardware. Its Telemetry thread is the ONLY
#     thing that touches the INA228 on this page. The old Arm Test page polls
#     I2C from the Tk thread in update_batt(); doing both at once would have
#     two threads sharing one SMBus object, which is not thread-safe. So here
#     the GUI never reads I2C - it only reads the module's state snapshot.
#
#   * update_propv2() runs on the Tk thread and only paints labels.
#
#   * each phase runs in a worker thread, because a phase blocks for up to 68 s
#     and the Tk event loop has to stay responsive for the STOP button.
#     Workers never touch widgets at all - they hand a callable to
#     propv2_post() and update_propv2() runs it on the Tk thread.

# Same colour language as set_arm_state() on the Arm Test page: white = safe
# to touch, yellow = precharging, green = live, blue = motors commanded,
# red = fault.
PROPV2_COLOURS = {
    "SAFE":        "white",
    "PRECHARGING": "yellow",
    "LIVE":        "green",
    "RUNNING":     "blue",
    "FAULT":       "red",
}


def propv2_post(fn):
    """
    Queue a UI update from a worker thread.

    Not root.after(0, ...) - Tkinter is not thread-safe and calling into it off
    the Tk thread can raise "main thread is not in main loop". Drained by
    update_propv2(), which is already running on the Tk thread.
    """
    propv2_ui_queue.put(fn)


def prop_v2():
    """Enter the Prop TEST V2 page."""
    global propv2_fault_latched, propv2_idle_watch, propv2_idle_note

    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    PropV2_f.pack(fill=BOTH, expand=TRUE)

    propv2_fault_latched = False

    # Drop anything a previous visit left queued, so stale callbacks cannot
    # repaint the page we are about to set up.
    while not propv2_ui_queue.empty():
        try:
            propv2_ui_queue.get_nowait()
        except queue.Empty:
            break

    # Open the gpiochip and force a known-safe state. Deliberately does NOT
    # precharge - that is the operator's first button. The LED claim is left to
    # session_power_up(), so there is only one place that does it.
    Precharge.INITIALIZE_SYSTEM()
    Precharge.CLOSE_FET()

    # Start sampling voltage/current right away, before anything is powered.
    # Without this the page could only ever say "probably safe"; with it, SAFE
    # is backed by an actual reading, and a miswired pack or a bus still
    # holding charge shows up the moment you open the page.
    propv2_idle_note = ""
    propv2_idle_watch = True
    # Clear any abort left over from a previous visit, or the fault watcher in
    # update_propv2() reads it as a fresh trip and e-stops on page entry.
    Hobbywing_Prop_Test.session_clear_fault()
    # Bin fault logs older than the retention window. Done on page entry so
    # tidying up happens as a side effect of using the rig - no cron needed.
    Hobbywing_Prop_Test.prune_logs()
    Hobbywing_Prop_Test.session_start_monitor(quiet=True)

    set_propv2_state("SAFE", "reading bus...")
    propv2_buttons_idle()

    # root.update() (not update_idletasks) so the frame is actually mapped, and
    # the monitor is started on a delay - same pattern as arm(). update_propv2()
    # stops itself when the page is not viewable, so if it ran before the frame
    # was mapped it would kill its own refresh loop on the first tick.
    root.update()
    root.after(100, start_propv2_monitor)


def start_propv2_monitor():
    global propv2_after_id
    if propv2_after_id is None:
        update_propv2()


def set_propv2_state(state, detail=""):
    """Paint the status corner. Tk thread only."""
    global propv2_state
    propv2_state = state
    propv2_dot.config(foreground=PROPV2_COLOURS.get(state, "white"))
    propv2_state_lbl.config(text=state)
    propv2_detail_lbl.config(text=detail)


def propv2_idle_readout(volts):
    """
    State for the unpowered page, decided by what the shunt actually reads.

    SAFE is an assertion about the hardware, so it is only made when there is a
    reading to back it up:

      * no reading      -> FAULT. The INA228 is not answering, so nothing else
                           on this page can be trusted either. Almost always
                           I2C wiring or the wrong address.
      * bus still up    -> FAULT. FET open and precharge off, yet there is
                           voltage: residual charge in the ESC caps, a FET that
                           is not opening, or a feed wired past the switch.
      * near zero       -> SAFE, with the measured value shown so the operator
                           can see it is a measurement and not an assumption.
    """
    if volts is None:
        return "FAULT", "no INA228 reading - check the I2C wiring"

    if volts > Hobbywing_Prop_Test.BUS_DEAD_MAX_V:
        return "FAULT", f"bus still at {volts:.2f} V with the FET open - do not touch"

    note = f"{propv2_idle_note} - " if propv2_idle_note else ""
    return "SAFE", f"{note}bus {volts:.2f} V - press Start Precharge"


def update_propv2():
    """
    Refresh the telemetry labels at 10 Hz from the module's state snapshot.

    get_state() just copies a dict under a lock - no I2C, no blocking - so this
    is safe to run on the Tk thread.
    """
    global propv2_after_id, propv2_fault_latched

    if not PropV2_f.winfo_viewable():
        propv2_after_id = None
        return

    # Apply whatever the worker threads handed over since the last tick.
    while True:
        try:
            fn = propv2_ui_queue.get_nowait()
        except queue.Empty:
            break
        try:
            fn()
        except Exception as e:
            print(f"[PROP V2 UI ERROR] {e}")

    try:
        snap = Hobbywing_Prop_Test.get_state()

        V, I, T = snap["volts"], snap["amps"], snap["temp_c"]

        propv2_v_lbl.config(text=f"Voltage:  {V:.2f} V" if V is not None else "Voltage:  --")
        propv2_i_lbl.config(text=f"Current:  {I:.2f} A" if I is not None else "Current:  --")
        propv2_w_lbl.config(
            text=f"Power:    {V * I:.0f} W" if (V is not None and I is not None) else "Power:    --"
        )
        propv2_t_lbl.config(text=f"Temp:     {T:.1f} C" if T is not None else "Temp:     --")

        # "off" means no frames at all, which is the ESC-beeping condition -
        # a genuinely different state from 1000 us, so it is shown as such.
        top = f"{snap['top_us']} us" if snap["top_us"] is not None else "off"
        bot = f"{snap['bot_us']} us" if snap["bot_us"] is not None else "off"
        propv2_pwm_lbl.config(text=f"PWM TOP: {top}    BOT: {bot}")

        # While idle, the status corner tracks the live reading so SAFE keeps
        # being re-confirmed rather than asserted once on page entry.
        if propv2_idle_watch:
            state, detail = propv2_idle_readout(V)
            set_propv2_state(state, detail)

        # An over-current or under-voltage trip happens on the telemetry
        # thread, which can only abort the phase - it cannot cut power or touch
        # widgets. So the Tk thread picks it up here and escalates to a full
        # emergency stop. Latched so it only fires once per precharge.
        reason = snap["abort_reason"]
        if (reason and not propv2_fault_latched
                and ("over-current" in reason or "under-voltage" in reason)):
            propv2_fault_latched = True
            print(f"[PROP V2] guard tripped: {reason}")
            propv2_estop(detail=reason)

    except Exception as e:
        propv2_detail_lbl.config(text=f"telemetry error: {e}")

    finally:
        propv2_after_id = root.after(100, update_propv2)


# --- progress bar -----------------------------------------------------------

def propv2_bar_start_for(key):
    global propv2_bar_running, propv2_bar_start, propv2_bar_duration
    propv2_bar_running = True
    propv2_bar_start = time.time()
    # Asks the module how long the phase is instead of hardcoding it here, so
    # editing the SEQUENCE table keeps the bar honest.
    propv2_bar_duration = Hobbywing_Prop_Test.phase_duration(key)
    propv2_bar["value"] = 0
    propv2_bar.pack(anchor="e", pady=(10, 0))
    propv2_bar_update()


def propv2_bar_update():
    if not propv2_bar_running:
        return
    elapsed = time.time() - propv2_bar_start
    propv2_bar["value"] = min((elapsed / propv2_bar_duration) * 100, 100)
    root.after(100, propv2_bar_update)


def propv2_bar_stop():
    global propv2_bar_running
    propv2_bar_running = False
    propv2_bar.pack_forget()


# --- button enable/disable --------------------------------------------------
# The emergency stop is never disabled. That is the whole point of it.

def propv2_test_buttons():
    return [PV2_TOP, PV2_BOT, PV2_BOTH, PV2_PULSE]


def propv2_buttons_idle():
    """Nothing powered: only the precharge button is usable."""
    PV2_PRECHARGE.config(state="normal", text="Start Precharge")
    PV2_PRECHARGE.configure(style="PropIdle.TButton")
    PV2_POWEROFF.config(state="disabled")       # nothing to power off
    PV2_POWEROFF.configure(style="PropIdle.TButton")
    PV2_LED.config(state="disabled", text="Turn LED On")
    PV2_LED.configure(style="PropIdle.TButton")
    for b in propv2_test_buttons():
        b.config(state="disabled")
        b.configure(style="PropIdle.TButton")


def propv2_buttons_live():
    """Bus up and idle: every test is available, and so is powering off."""
    PV2_PRECHARGE.config(state="disabled", text="Precharged")
    PV2_PRECHARGE.configure(style="PropOn.TButton")
    PV2_POWEROFF.config(state="normal")
    PV2_POWEROFF.configure(style="PropIdle.TButton")
    PV2_LED.config(state="normal")
    PV2_LED.configure(style="PropOn.TButton" if PV2_LED.cget("text") == "Turn LED Off" else "PropIdle.TButton")
    for key, b in zip(("top", "bot", "both", "pulse"), propv2_test_buttons()):
        b.config(state="normal", text=Hobbywing_Prop_Test.PHASE_TITLES[key])
        b.configure(style="PropIdle.TButton")


def propv2_buttons_busy(active):
    """
    A phase is running. Lock out everything except the active button (which
    becomes CANCEL) and the emergency stop.

    Locking the others matters: starting a second phase while one is running
    would have two worker threads commanding the same two ESCs.

    Power Off is locked out too. Cutting power with the motors spinning is the
    emergency case, not the normal one, and the emergency stop is the button
    for that - it is the only one that is never disabled.
    """
    PV2_PRECHARGE.config(state="disabled")
    PV2_POWEROFF.config(state="disabled")
    PV2_LED.config(state="disabled")
    for b in propv2_test_buttons():
        if b is active:
            b.config(state="normal", text="CANCEL")
            b.configure(style="PropBusy.TButton")
        else:
            b.config(state="disabled")


# --- handlers ---------------------------------------------------------------

def propv2_precharge():
    """
    Button 1. Precharge, close the FET, start telemetry - but no PWM frames.

    Runs in a worker because power_up() polls the bus voltage for up to 3 s and
    we do not want the window frozen while it does.
    """
    global propv2_fault_latched, propv2_idle_watch, propv2_idle_note

    if Hobbywing_Prop_Test.session_live():
        return

    propv2_fault_latched = False
    propv2_idle_watch = False       # the handler owns the status from here on
    propv2_idle_note = ""
    propv2_stop.clear()
    set_propv2_state("PRECHARGING", "charging bus through the resistor")
    PV2_PRECHARGE.config(state="disabled")

    def worker():
        try:
            csv_path = Hobbywing_Prop_Test.session_power_up(guards_enabled=True, quiet=True)

            def done():
                # No frames yet, so the ESCs are beeping. Say so, because the
                # operator is meant to be listening for exactly that.
                set_propv2_state("LIVE", "no signal - ESCs should beep 1/s")
                propv2_buttons_live()
                print(f"[PROP V2] logging to {csv_path}")

            propv2_post(done)

        except Exception as e:
            # Bind the message to a local NOW. Python deletes the `as e` name
            # when the except block ends, and this closure runs later off the
            # UI queue - referencing `e` in there raises, which left the page
            # stuck in PRECHARGING with every button locked out.
            msg = str(e)
            print(f"[PROP V2 PRECHARGE ERROR] {msg}")

            def failed():
                # The FET was never closed, so the rig is safe - hand the
                # status corner back to the idle readout, carrying the reason.
                global propv2_idle_watch, propv2_idle_note
                set_propv2_state("FAULT", msg)
                propv2_idle_note = "precharge failed"
                propv2_idle_watch = True
                propv2_buttons_idle()

            propv2_post(failed)

    threading.Thread(target=worker, daemon=True).start()


def propv2_power_off():
    """
    Button: normal end-of-test power-down. LIVE -> SAFE.

    The counterpart to Start Precharge, and the one to use when the test is
    simply finished: it de-energises exactly as hard as the emergency stop
    does, but without flagging a fault, so a clean run still bins its log.

    Disabled while a phase is running. Cutting power with the motors spinning
    is the emergency case, and that button is right there.
    """
    global propv2_fault_latched, propv2_idle_watch, propv2_idle_note

    if not Hobbywing_Prop_Test.session_live():
        return

    propv2_stop.set()

    try:
        kept = Hobbywing_Prop_Test.session_power_off()
    except Exception as e:
        print(f"[PROP V2 POWER OFF ERROR] {e}")
        kept = None

    propv2_bar_stop()
    PV2_LED.config(text="Turn LED On")

    propv2_fault_latched = False
    note = "powered down"
    if kept:
        # Something earlier in the run flagged itself, so the log survived even
        # though this was a normal shutdown. Say so.
        note += f", log: {os.path.basename(kept)}"
    propv2_idle_note = note
    propv2_idle_watch = True
    set_propv2_state("SAFE", f"{note} - reading bus...")

    propv2_buttons_idle()
    root.update_idletasks()


def propv2_estop(detail="operator pressed STOP"):
    """
    Button 2. Cut everything: throttle to safe, frames off, LED off, FET off,
    precharge off, gpiochip released.

    Runs synchronously on the Tk thread on purpose. An emergency stop queued
    behind a worker thread is not an emergency stop. session_emergency_stop()
    is written to be safe to call mid-phase and safe to call twice.
    """
    global propv2_fault_latched, propv2_idle_watch, propv2_idle_note

    propv2_stop.set()

    try:
        Hobbywing_Prop_Test.session_emergency_stop()
    except Exception as e:
        print(f"[PROP V2 E-STOP ERROR] {e}")

    propv2_bar_stop()
    PV2_LED.config(text="Turn LED On")

    kept = Hobbywing_Prop_Test.session_csv_path()

    if "over-current" in detail or "under-voltage" in detail:
        # A guard trip stays pinned in red with its reason until the operator
        # precharges again. Handing it to the idle readout would let it fade to
        # SAFE as the bus decays, and the reason would be gone off the screen
        # before anyone had read it.
        propv2_idle_watch = False
        # Name the log on screen, or nobody will know it was kept.
        log_note = f" - log: {os.path.basename(kept)}" if kept else ""
        set_propv2_state("FAULT", f"{detail}{log_note}")
    else:
        # Normal stop: the idle readout takes over, so the operator watches the
        # bus decay and gets a measured SAFE rather than an assumed one.
        propv2_fault_latched = False
        propv2_idle_note = detail if not kept else f"{detail}, log: {os.path.basename(kept)}"
        propv2_idle_watch = True
        set_propv2_state("SAFE", f"{detail} - reading bus...")

    propv2_buttons_idle()
    # update_idletasks() and not update(): this can be reached from inside the
    # update_propv2() after-callback when a guard trips, and a full update()
    # there would re-enter the event loop.
    root.update_idletasks()


def propv2_led():
    """Button 3. LED on/off. Needs the bus live, same as the Arm Test page."""
    if not Hobbywing_Prop_Test.session_live():
        set_propv2_state("FAULT", "precharge before using the LED")
        return

    if PV2_LED.cget("text") == "Turn LED On":
        LED.LED_ON()
        PV2_LED.config(text="Turn LED Off")
        PV2_LED.configure(style="PropOn.TButton")
    else:
        LED.LED_OFF()
        PV2_LED.config(text="Turn LED On")
        PV2_LED.configure(style="PropIdle.TButton")


def propv2_run_phase(key, button):
    """
    Buttons 4-7. Run one phase from the module's SEQUENCE table.

    Second press of the same button cancels: that is a controlled stop (both
    channels to 1000 us, hold) rather than the power cut the STOP button does.
    """
    global propv2_running, propv2_idle_watch

    if button.cget("text") == "CANCEL":
        Hobbywing_Prop_Test.session_cancel_phase()
        button.config(text="cancelling...", state="disabled")
        return

    if propv2_running:
        return

    if not Hobbywing_Prop_Test.session_live():
        set_propv2_state("FAULT", "precharge first")
        return

    title = Hobbywing_Prop_Test.PHASE_TITLES[key]
    propv2_running = True
    propv2_idle_watch = False       # handler owns the status while a phase runs
    propv2_stop.clear()
    set_propv2_state("RUNNING", title)
    propv2_buttons_busy(button)
    propv2_bar_start_for(key)

    def worker():
        global propv2_running
        ok = False
        try:
            ok = Hobbywing_Prop_Test.session_run_phase(key)

        except Exception as e:
            print(f"[PROP V2 PHASE ERROR] {e}")
            # Keeps this run's log so the failure can be looked at.
            Hobbywing_Prop_Test.mark_log_keep(f"{title} failed: {e}")

        finally:
            propv2_running = False

            def finish():
                propv2_bar_stop()

                # session_emergency_stop() may have run while we were in here,
                # in which case the page is already in FAULT/STOPPED and must
                # not be dragged back to LIVE.
                if not Hobbywing_Prop_Test.session_live():
                    return

                propv2_buttons_live()
                if ok:
                    set_propv2_state("LIVE", f"{title} complete - at {Hobbywing_Prop_Test.US_SAFE} us")
                else:
                    set_propv2_state("LIVE", f"{title} cancelled - at {Hobbywing_Prop_Test.US_SAFE} us")

            propv2_post(finish)

    threading.Thread(target=worker, daemon=True).start()


# Thin wrappers so each button has its own command with no late-binding trap.
def propv2_top():
    propv2_run_phase("top", PV2_TOP)


def propv2_bot():
    propv2_run_phase("bot", PV2_BOT)


def propv2_both():
    propv2_run_phase("both", PV2_BOTH)


def propv2_pulse():
    propv2_run_phase("pulse", PV2_PULSE)
#####*****END CHANGES*****#####

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
    #####*****CHANGES*****#####
    # Opening the page no longer starts the test. It used to, which meant the
    # Ethernet and SBUS buttons were unreachable for the ~55 s the body test
    # takes - you had to sit through a full run (two flight controller reboots)
    # before you could do anything else on this page. Now the page just shows,
    # and the test waits for the Start button.
    global body_result_note
    body_result_note = ""                               # clear last run's verdict
    body_stop.clear()
    body_reset_labels()
    main.pack_forget()
    back_b.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    Body_f.pack(fill=BOTH, expand=TRUE)
    body_lock_nav(False)        # nothing running: everything available
    #####*****END CHANGES*****#####

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

PRECHARGE_TIMEOUT = 3000
PRECHARGE_CHECK_INTERVAL = 200
PRECHARGE_MIN_VOLTAGE = 21.0

precharge_start_time = None
precharge_good_count = 0

def arm_red():
    PWR.configure(style="ArmDanger.TButton")

def arm_reset():
    PWR.configure(style="Arm.TButton")
    for button in [PWM_INIT, SPIN_ALL, SPIN_TOP, SPIN_BOT, LED_btn, PROP]:
        button.configure(style="Arm.TButton")


def PWR_ON():
    global pwr_after_id
    global precharge_start_time
    global precharge_good_count

    try:
        spin_stop.clear()
        LED.LED_OFF()
        Precharge.INITIALIZE_SYSTEM()
        Precharge.START_PRECHARGE()

        precharge_start_time = time.time()
        precharge_good_count = 0

        set_arm_state("PRECHARGE")

        pwr_after_id = PWR.after(
            PRECHARGE_CHECK_INTERVAL,
            PWR_CHECK
        )

    except Exception as e:
        print(f"[PWR ON ERROR] Cannot start precharge: {e}")

        set_arm_state("FAULT")
        Precharge.CLOSE_FET()
        PWR.config(text="Precharge FAIL")

def toggle_power():
    global arm_powered

    if not arm_powered:
        PWR_ON()
        arm_powered = True
        PWR.config(text="POWER OFF")
        arm_red()
    else:
        power_off()
        arm_powered = False
        PWR.config(text="POWER ON")
        arm_reset()


def PWR_CHECK():
    global pwr_after_id
    global precharge_good_count

    try:
        elapsed = (time.time() - precharge_start_time) * 1000

        Precharge.OPEN_FET()   #force fet open for now until fix precharge issue then remove this line!!. 

        LED.LED_OFF() 

        if elapsed >= PRECHARGE_TIMEOUT:
            print("[PWR CHECK] Precharge timeout")

            Precharge.CLOSE_FET()
            Precharge.TURN_OFF_PRECHARGE()
            pwr_after_id = None
            set_arm_state("FAULT")
            PWR.config(text="Check Battery")
            return


        voltage = Batt_monitor.read_battery_voltage()

        if voltage is not None and voltage >= PRECHARGE_MIN_VOLTAGE:
            precharge_good_count += 1
            print(f"[PWR CHECK] Voltage OK {voltage:.2f}V ({precharge_good_count}/2)")

        else:
            precharge_good_count = 0
            print(f"[PWR CHECK] Voltage low {voltage}")


        if precharge_good_count >= 2:

            print("[PWR CHECK] Precharge successful")

            Precharge.OPEN_FET()

            root.update()

            Precharge.TURN_OFF_PRECHARGE()

            Spin_test.claim_pwm_pins()

            set_arm_state("LIVE")
            
            pwr_after_id = None
            return


        pwr_after_id = PWR.after(
            PRECHARGE_CHECK_INTERVAL,
            PWR_CHECK
        )


    except Exception as e:
        print(f"[PWR CHECK ERROR] {e}")

        Precharge.CLOSE_FET()
        Precharge.TURN_OFF_PRECHARGE()

        set_arm_state("FAULT")
        PWR.config(text="Power ERROR")

def run_spin_toggle(button, default_text, status_text, duration, spin_function):



    # Cancel current spin
    if button.cget("text") == "Cancel Spin":

        spin_stop.set()

        try:
            Spin_test.SPIN_CNCL()
        except:
            pass

        stop_spin_progress()

        set_arm_state("LIVE")

        button.config(text=default_text)


        button.configure(style="Arm.TButton")




        return


    if current_state != "LIVE":
        set_arm_state("FAULT")
        return


    spin_stop.clear()
    button.configure(style="ArmSuccess.TButton")



    button.config(text="Cancel Spin")


    def worker():

        try:

            set_arm_state("SPINNING")

            root.after(
                0,
                lambda: start_spin_progress(status_text, duration)
            )


            spin_function()


        except Exception as e:

            print(f"[SPIN ERROR] {e}")

            Spin_test.SPIN_STOP()

            set_arm_state("FAULT")


        finally:
            try:
                Spin_test.SPIN_STOP()
            except:
                pass

            root.after(0, stop_spin_progress)

            def reset_spin_button():
                button.config(text=default_text)
                button.configure(style="Arm.TButton")

            root.after(0, reset_spin_button)

            if not spin_stop.is_set():
                set_arm_state("LIVE")



    threading.Thread(
        target=worker,
        daemon=True
    ).start()

def update_pwm_status():
    try:
        pwm = Spin_test.get_pwm_state()

        pwm1 = pwm["PWM1"] if pwm["PWM1"] is not None else "--"
        pwm2 = pwm["PWM2"] if pwm["PWM2"] is not None else "--"

        lpwm_status.config(
            text=f"PWM1: {pwm1}   PWM2: {pwm2}"
        )

    except Exception:
        lpwm_status.config(
            text="PWM1: --   PWM2: --"
        )

    root.after(100, update_pwm_status)

def INITIAL_PWM():

    run_spin_toggle(
        PWM_INIT,
        "Initialise PWM",
        "INITIALISE PWM",
        6,
        Spin_test.SPIN_INIT
    )



def SPIN():

    run_spin_toggle(
        SPIN_ALL,
        "Spin ALL",
        "SPIN ALL",
        8,
        Spin_test.SPIN_START
    )



def TOP_SPIN():

    run_spin_toggle(
        SPIN_TOP,
        "Spin TOP",
        "SPIN TOP",
        6,
        Spin_test.SPIN_TOP
    )



def BOT_SPIN():

    run_spin_toggle(
        SPIN_BOT,
        "Spin BOT",
        "SPIN BOT",
        6,
        Spin_test.SPIN_BOT
    )



def PROP_SPIN():

    run_spin_toggle(
        PROP,
        "Prop Test",
        "PROP TEST",
        39,
        Spin_test.SPIN_PROP
    )

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
    if current_state != "LIVE":
        set_arm_state("FAULT")
        return

    if LED_btn.cget("text") == "Turn LED On":
        LED.LED_ON()
        LED_btn.config(text="Turn LED Off")
        LED_btn.configure(style="ArmSuccess.TButton")

    else:
        LED.LED_OFF()
        LED_btn.config(text="Turn LED On")
        LED_btn.configure(style="Arm.TButton")



def power_off():
    global pwr_after_id, arm_powered

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
        Precharge.CLOSE_FET()
    except:
        pass

    set_arm_state("IDLE")
    arm_powered = False
    PWR.config(text="POWER ON")
    PWR.configure(style="Arm.TButton")
    LED_btn.config(text="Turn LED On")
    LED_btn.configure(style="Arm.TButton")
    arm_reset()


def update_batt():
    global batt_after_id

    if not Arm_f.winfo_viewable():
        batt_after_id = None
        return

    try:
        V = Batt_monitor.read_battery_voltage()
        I = Batt_monitor.read_battery_current()
        T = Batt_monitor.read_battery_temperature()

        if V is not None:
            lv.config(text=f"Voltage: {V:.2f} V")
        else:
            lv.config(text="Voltage: --")

        if I is not None:
            li.config(text=f"Current: {I:.2f} A")
        else:
            li.config(text="Current: --")

        if T is not None:
            lt.config(text=f"Temperature: {T:.2f} C")
        else:
            lt.config(text="Temperature: --")

    finally:
        batt_after_id = root.after(100, update_batt)
        

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
    #####*****CHANGES*****#####
    # Wrapped: if the port does not exist at all, mavlink_connection() raises
    # and the whole body test used to die with a traceback. A missing link is a
    # FAIL, not a crash.
    try:
        serial_result = Body_Serial_test.serial_test()
    except Exception as e:
        print(f"[BODY] serial test error: {e}")
        serial_result = False
    #####*****END CHANGES*****#####
    if body_stop.is_set():
        return
    ls.after(0, lambda: ls.config(text="Heartbeat received - PASS" if serial_result else "No Heartbeat - FAIL", bootstyle=SUCCESS if serial_result else DANGER, font=(None, 14)))

    #####*****CHANGES*****#####
    # No heartbeat means no MAVLink link, and all three remaining sections need
    # one: the analog port and PWM tests write parameters and reboot the FC
    # over it, and the CAN test needs the FC alive at the other end. Running
    # them anyway would burn ~40 s of timeouts and report three more failures
    # that all have the same single cause, which buries the real one.
    #
    # Stopping here also releases the navigation lock straight away (the
    # watchdog sees the thread end), so the fix-and-rerun loop is quick.
    if not serial_result:
        print("[BODY] no heartbeat - skipping analog port, CAN and PWM tests")
        for widget in (la, lcan, lpwm):
            widget.after(0, lambda w=widget: w.config(
                text="SKIPPED - needs the serial link",
                bootstyle=WARNING,
                font=(None, 14),
            ))
        # Plain assignment, no Tk call: body_lock_nav(False) renders this when
        # the watchdog lifts the lock. Setting the label here instead would
        # race with that same call clearing it.
        global body_result_note
        body_result_note = ("Stopped at the serial test: Fix the link and run "
                            "Body Test again.")
        return
    #####*****END CHANGES*****#####

    time.sleep(0.5)
    if body_stop.is_set():
        return

    la.after(0, lambda: la.config(text="Running Analog Port test (Rebooting)...", bootstyle=INFO, font=(None, 14)))
    output = Analog_port_test.analog_port_run()
    if body_stop.is_set():
        return
    
    combined_output = f"Results: A1={output[0]:.2f} V, A2={output[1]:.2f} V"

    board1 = (0.7 <= output[0] <= 0.9) and (1.5 <= output[1] <= 1.7)
    board2 = (1.1 <= output[0] <= 1.3) and (2.3 <= output[1] <= 2.5)

    if board1 or board2:
        la.after(0, lambda: la.config(text=f"PASS -- {combined_output}", bootstyle=SUCCESS, font=(None, 14)))
    elif (output[0] == -1) or (output[1] == -1):
        la.after(0, lambda: la.config(text="FAIL -- COULDNT WRITE PARAMS - CHECK CFG", bootstyle=DANGER, font=(None, 14)))
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
    #####*****CHANGES*****#####
    # Last reboot of the run happens inside here. try/finally so the
    # navigation lock is released even if the PWM test raises - otherwise a
    # failure here would strand the operator on this page.
    try:
        pwm_result = PWM_test.run_pwm_test()
    finally:
        body_pwm_done.set()     # body_nav_watch() unlocks within 300 ms
    #####*****END CHANGES*****#####
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
#####*****CHANGES*****#####
# New entry on the home screen. b7's bottom padding moved onto b8 so the
# button block stays centred the way it was.
b7.pack_configure(pady=0)
b8 = ttk.Button(main, text="Prop TEST V2", bootstyle=PRIMARY, width=30, command=prop_v2); b8.pack(expand=TRUE, pady=(0,50))
#####*****END CHANGES*****#####

home_b = ttk.Button(root, text="Home", bootstyle=OUTLINE, command=home, width=10)
back_b = ttk.Button(root, text="Back", bootstyle=OUTLINE, command=show_body_from_back, width=10)

# Body buttons
eth1 = ttk.Button(Body_f, text="Ethernet Test", bootstyle=SECONDARY, width=20, command=Eth); eth1.pack(expand=TRUE, anchor=E, padx=75)
SB1 = ttk.Button(Body_f, text="Infravision SBUS (15-pin)", bootstyle=SECONDARY, width=20, command=SBUS_INF); SB1.pack(expand=TRUE, anchor=E, padx=75)
SB2 = ttk.Button(Body_f, text="Standard SBUS (9-pin)", bootstyle=SECONDARY, width=20, command=SBUS); SB2.pack(expand=TRUE, anchor=E, padx=75)
Debug = ttk.Button(Body_f, text="Debug Mode", bootstyle=SECONDARY, width=20); #Debug.pack(expand=TRUE, anchor=E, padx=75)   #hidden for now until we work this out

#####*****CHANGES*****#####
# Start/Stop for the four-section body test, which no longer auto-runs on page
# entry. Packed with before=eth1 so they sit at the TOP of the right-hand
# column: they are created down here because `command=` needs the handlers to
# exist already, but they belong above the sub-test buttons visually.
BODY_START = ttk.Button(Body_f, text="Start Body Test", bootstyle=SUCCESS, width=20, command=body_start)
BODY_START.pack(expand=TRUE, anchor=E, padx=75, before=eth1)

BODY_STOP = ttk.Button(Body_f, text="Stop Body Test", bootstyle=DANGER, width=20, command=body_stop_test)
BODY_STOP.pack(expand=TRUE, anchor=E, padx=75, before=eth1)

# Nothing running yet, so Stop starts out dead.
BODY_STOP.config(state="disabled")
#####*****END CHANGES*****#####

# Arm buttons
# Arm buttons
PWR = ttk.Button(Arm_f, text="POWER ON", bootstyle=PRIMARY, style="Arm.TButton", width=24, command=toggle_power)
PWR.pack(expand=TRUE, pady=(25, 15))

PWM_INIT = ttk.Button(Arm_f, text="Intialise PWM", bootstyle=SECONDARY, style="Arm.TButton", width=24, command=INITIAL_PWM)
PWM_INIT.pack(expand=TRUE, pady=5)

SPIN_ALL = ttk.Button(Arm_f, text="Spin ALL", bootstyle=SECONDARY, style="Arm.TButton", width=24, command=SPIN)
SPIN_ALL.pack(expand=TRUE, pady=5)

SPIN_TOP = ttk.Button(Arm_f, text="Spin TOP", bootstyle=SECONDARY, style="Arm.TButton", width=24, command=TOP_SPIN)
SPIN_TOP.pack(expand=TRUE, pady=5)

SPIN_BOT = ttk.Button(Arm_f, text="Spin BOT", bootstyle=SECONDARY, style="Arm.TButton", width=24, command=BOT_SPIN)
SPIN_BOT.pack(expand=TRUE, pady=5)

LED_btn = ttk.Button(Arm_f, text="Turn LED On", bootstyle=SECONDARY, style="Arm.TButton", width=24, command=TOGGLE_LED)
LED_btn.pack(expand=TRUE, pady=5)

PROP = ttk.Button(Arm_f, text="Prop Test", bootstyle=SECONDARY, style="Arm.TButton", width=24, command=PROP_SPIN)
PROP.pack(expand=TRUE, pady=5)

STOP_btn = ttk.Button(batt_container, text="STOP", style="Stop.TButton", width=12, command=power_off)
STOP_btn.pack(pady=10)

#####*****CHANGES*****#####
# --------------------------------------------------------------------------
# Prop TEST V2 page - the 7 buttons
# --------------------------------------------------------------------------
# Created down here rather than next to the labels because `command=` is
# evaluated right now, so the handlers above have to already exist.

propv2_btns = ttk.Frame(PropV2_f)
propv2_btns.pack(side=LEFT, fill=BOTH, expand=TRUE, padx=50)

propv2_title = ttk.Label(propv2_btns, text="PROP TEST V2", bootstyle=PRIMARY, font=(None, 26, "bold"))
propv2_title.pack(pady=(25, 5))

# 1. Precharge
PV2_PRECHARGE = ttk.Button(propv2_btns, text="Start Precharge", style="PropIdle.TButton", width=26, command=propv2_precharge)
PV2_PRECHARGE.pack(expand=TRUE, pady=6)

# 2. Power off - the opposite of precharge, so it sits next to it. Normal
#    end-of-test shutdown: de-energises just as hard as the emergency stop but
#    without flagging a fault, so a clean run still bins its log.
PV2_POWEROFF = ttk.Button(propv2_btns, text="Power Off", style="PropIdle.TButton", width=26, command=propv2_power_off)
PV2_POWEROFF.pack(expand=TRUE, pady=6)

# 3. Emergency stop. Bigger style and extra padding above/below so it is hard
#    to hit by accident and impossible to miss when you need it.
PV2_ESTOP = ttk.Button(propv2_btns, text="EMERGENCY STOP", style="EStop.TButton", width=22, command=propv2_estop)
PV2_ESTOP.pack(expand=TRUE, pady=(18, 18))

# 4. LED
PV2_LED = ttk.Button(propv2_btns, text="Turn LED On", style="PropIdle.TButton", width=26, command=propv2_led)
PV2_LED.pack(expand=TRUE, pady=6)

# 5-8. The four phases from Hobbywing_Prop_Test.SEQUENCE
PV2_TOP = ttk.Button(propv2_btns, text="TOP Motor Test", style="PropIdle.TButton", width=26, command=propv2_top)
PV2_TOP.pack(expand=TRUE, pady=6)

PV2_BOT = ttk.Button(propv2_btns, text="BOT Motor Test", style="PropIdle.TButton", width=26, command=propv2_bot)
PV2_BOT.pack(expand=TRUE, pady=6)

PV2_BOTH = ttk.Button(propv2_btns, text="BOTH Motors Test", style="PropIdle.TButton", width=26, command=propv2_both)
PV2_BOTH.pack(expand=TRUE, pady=6)

PV2_PULSE = ttk.Button(propv2_btns, text="Pulse Test", style="PropIdle.TButton", width=26, command=propv2_pulse)
PV2_PULSE.pack(expand=TRUE, pady=(6, 25))

# Everything except the precharge starts locked out.
propv2_buttons_idle()
#####*****END CHANGES*****#####



# Loom test page
l20 = ttk.Label(loom_f, text="Ready to test", bootstyle=PRIMARY, font=(None, 24)); l20.pack(pady=20)
l21 = ttk.Label(loom_f, text="", bootstyle=PRIMARY); l21.pack(expand=TRUE)
ttk.Button(loom_f, text="Run Test", bootstyle=SECONDARY, width=15, command=loom_test).pack(pady=25)

main.pack(fill=BOTH, expand=True)
update_pwm_status()
root.mainloop()