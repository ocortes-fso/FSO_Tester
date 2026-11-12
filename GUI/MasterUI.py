import time
import ttkbootstrap as ttk 
from ttkbootstrap.constants import *
import sys
import os
import numpy as np
from tkinter import BOTH, TRUE
import tkinter as tk          #####*****CHANGES*****##### Canvas, for the round E-STOP
import threading
import queue                    #####*****CHANGES*****##### worker -> Tk thread handoff

# --- GUI Setup ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
#####*****CHANGES*****#####
# Hobbywing_Prop_Test added for the new "Prop TEST V2" page.
# Manual_PWM_Test added for the new "Cv2_A06 Testing" page.
#
# Spin_test is still imported and still used by the Arm Test page's code, which
# is kept but no longer reachable from the menu - see the main menu buttons at
# the bottom of this file.
from Subcodes import reset, Magnetometer, Lidar, Network_test, Arm_loom_test, Rear_switch_plate_test, Body_Serial_test, PWM_test, SBUS_test, Analog_port_test, Analog, Can_test, INF_SBUS, Spin_test, LED, Precharge, Batt_monitor, Hobbywing_Prop_Test, Manual_PWM_Test
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

#####*****CHANGES*****#####
# --- Cv2_A06 Testing page state ---
# Manual PWM: two sliders and two canned 3-second nudges. See
# Subcodes/Manual_PWM_Test.py for why it does not reuse the scripted test's
# PWM class.
#
# Its own stop Event again, and registered with Manual_PWM_Test rather than
# with Hobbywing_Prop_Test: that module already has propv2_stop registered
# against it, and handing it a second event would quietly break cancelling on
# the Prop TEST V2 page. The two pages abort independently.
a06_stop = threading.Event()
Manual_PWM_Test.register_stop_event(a06_stop)

a06_after_id = None            # handle for the label refresh loop
a06_state = "NO POWER"
a06_running = False            # True while a timed spin worker thread is alive
a06_spin_channel = None        # which channel that worker is driving
a06_spin_remaining = 0.0       # countdown, written by the worker, read by the Tk loop
a06_fault_latched = False      # so a guard trip is only escalated once
a06_idle_watch = False         # see the identically-named Prop V2 flag
a06_idle_note = ""
a06_ui_queue = queue.Queue()   # worker -> Tk thread, same reason as Prop V2

# True while THIS code is calling Scale.set(). ttk.Scale fires its `command`
# for programmatic changes exactly as it does for a drag, so resetting a slider
# would re-enter the move handler and command the PWM again. The guard makes
# "reset" mean reset.
a06_slider_echo = False

# Whether each slider is off its resting position, i.e. commanding throttle.
# Cached rather than read from the widget on every drag event, so the control
# refresh only runs on the transition instead of once per pixel of travel.
a06_hot = {"top": False, "bot": False}

#####*****CHANGES*****#####
# True while the arming worker is in its hold. Its own flag rather than reading
# Manual_PWM_Test.is_armed(), because during the hold neither "armed" nor "not
# armed" is the useful answer - the controls have to stay locked either way.
a06_arming = False

# --- slider rate limiting -------------------------------------------------
# The slider handler used to call lgpio straight through on every motion
# event, on the Tk thread. On the Pi that made the slider crawl at roughly
# 5 us/second: each event tore the software waveform down and built a new one
# (because the resting position used to mean "frames off", so dragging near
# the bottom crossed that boundary over and over), and the widget could not
# track the finger while it waited.
#
# Now a drag only records where the finger is and schedules one flush. The
# hardware write happens at most every A06_SLIDER_FLUSH_MS, decoupled from how
# fast the events arrive, so finger tracking never waits on lgpio. 40ms is
# 25 Hz - far finer than anyone can aim on a touchscreen, and the ESC is only
# reading one frame every 2.5ms anyway.
a06_slider_pending = {}        # channel -> us waiting to go to the hardware
a06_slider_flush_id = None     # the scheduled flush, or None if none is due
A06_SLIDER_FLUSH_MS = 40
#####*****END CHANGES*****#####

#####*****CHANGES*****#####
# --- Loom test state ---
# The loom test is a continuity scan, so what you want while wiggling a
# connector is a reading that keeps refreshing, not one you have to re-request.
# Start puts it on a 2s repeat; Stop ends it. Nothing runs on page entry, and
# the results are cleared when you arrive so a reading from a previous visit
# cannot be mistaken for a live one - which is what made it look like it was
# running by itself.
loom_after_id = None           # the scheduled next pass, or None if stopped
loom_running = False
LOOM_PERIOD_MS = 2000
#####*****END CHANGES*****#####
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
#####*****CHANGES*****#####
# NO LONGER USED - the emergency stop is a Canvas circle in the bottom-right
# corner now, not a ttk button, so it paints its own colours. Kept in case it
# goes back to being a normal button.
# style.configure("EStop.TButton", font=(None, 28, "bold"), padding=22, background="#b02a37", foreground="white")
#####*****END CHANGES*****#####
style.configure("PropIdle.TButton", font=(None, 18, "bold"), padding=4, background="#0d6efd", foreground="white")
style.configure("PropBusy.TButton", font=(None, 18, "bold"), padding=4, background="#fd7e14", foreground="white")
style.configure("PropOn.TButton", font=(None, 18, "bold"), padding=4, background="#198754", foreground="white")

# Cv2_A06 Testing page. Smaller than the Prop V2 styles because the power/LED
# row sits side by side rather than stacked, and the page has to carry two
# sliders as well as its buttons on a 480px-high screen.
style.configure("A06Small.TButton", font=(None, 14, "bold"), padding=4, background="#0d6efd", foreground="white")
style.configure("A06SmallOn.TButton", font=(None, 14, "bold"), padding=4, background="#198754", foreground="white")
# Spin / STOP per channel. The STOP variants are red on purpose: the button
# changes meaning when its slider is live, and colour is the fastest way to
# notice that the thing you are about to press now does the opposite.
style.configure("A06Spin.TButton", font=(None, 16, "bold"), padding=3, background="#0d6efd", foreground="white")
style.configure("A06Stop.TButton", font=(None, 16, "bold"), padding=3, background="#dc3545", foreground="white")
style.configure("A06Busy.TButton", font=(None, 16, "bold"), padding=3, background="#fd7e14", foreground="white")

# Main menu, now two groups side by side. Smaller than the old single column
# because two columns of the old size came to 1132px against the 800px the
# 5-inch screen has - measured, not estimated. At font 17 a 22-character
# button is about 295px, so the pair plus their gutters comes to roughly 650px
# and still leaves room.
#
# NAMED "Nav", NOT "Menu", AND THAT MATTERS.
# ttkbootstrap works out which widget a custom style belongs to by searching
# the style name for one of its widget-class words, and "menu" is one of them
# (Keywords.CLASSES holds 'button', 'label', 'menubutton', 'optionmenu',
# 'menu', ...). So "Menu.TButton" contains TWO of them, 'button' and 'menu',
# and which one wins depends on the order ttkbootstrap happens to scan that
# list in - i.e. on the installed version. Where 'menu' wins it then tries to
# call StyleBuilderTTK.create_menu_style(), which does not exist, and the GUI
# dies on this line at import time.
#
# The rule for any new style here: the name must contain exactly ONE of those
# class words, the one for the widget it is actually for. "Nav" and "NavHead"
# match only 'button' and 'label'. There is a check for this in the test
# harness so it cannot come back.
style.configure("Nav.TButton", font=(None, 17, "bold"), padding=7, background="#0d6efd", foreground="white")
style.configure("NavHead.TLabel", font=(None, 17, "bold"))
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
A06_f = ttk.Frame(root)         #####*****CHANGES*****##### Cv2_A06 Testing page

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

#####*****CHANGES*****#####
# Why the power-on was refused. Precharge is disabled (faulty hardware) and the
# FET now only closes if the input voltage checks out, so when it does not the
# operator needs the reason on screen - "Check Battery" on the button did not
# say whether the pack was missing, flat, or the monitor unreachable.
arm_reason = ttk.Label(status_container, text="", bootstyle=SECONDARY,
                       font=(None, 13), wraplength=320, justify="left")
arm_reason.pack(anchor="w")
#####*****END CHANGES*****#####


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
propv2_side.pack(side=RIGHT, anchor=NE, padx=20, pady=10)   #####*****CHANGES*****##### was padx=25 pady=20

propv2_dot = ttk.Label(propv2_side, text="●", font=("Arial", 26, "bold"), foreground="white")   #####*****CHANGES*****##### was 34
propv2_dot.pack(anchor="e")

propv2_state_lbl = ttk.Label(propv2_side, text="NO POWER", bootstyle=SECONDARY, font=(None, 22, "bold"))
propv2_state_lbl.pack(anchor="e")

# Second line of the status: which phase/step, or why we faulted.
propv2_detail_lbl = ttk.Label(propv2_side, text="press Power On", bootstyle=INFO, font=(None, 13))
propv2_detail_lbl.pack(anchor="e", pady=(0, 10))   #####*****CHANGES*****##### was 18

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
propv2_pwm_lbl.pack(anchor="e", pady=(10, 0))   #####*****CHANGES*****##### was 16

propv2_bar = ttk.Progressbar(propv2_side, maximum=100, bootstyle=INFO, length=220)
#####*****END CHANGES*****#####

#####*****CHANGES*****#####
# --------------------------------------------------------------------------
# Cv2_A06 Testing page - status / telemetry column
# --------------------------------------------------------------------------
# Same arrangement and the same colour language as the Prop TEST V2 page, so
# an operator who knows one page can read the other without relearning it.
# Separate widgets rather than shared ones because both pages can be left
# half-torn-down and sharing labels would have each page's refresh loop
# fighting over them.
#
# The voltage / current / temperature numbers come from Hobbywing_Prop_Test's
# telemetry thread (the only thing on the GUI that reads the INA228), and the
# PWM numbers come from Manual_PWM_Test, which owns the frames on this page.
#
# ONE DIFFERENCE FROM THE PROP V2 PAGE, and it is a deliberate fix rather than
# a style choice: the status DETAIL line lives in the left-hand column here,
# not in this one.
#
# Two reasons, both found by measuring the page at 800x480 rather than by
# looking at it:
#
#   * every widget in this column is now a fixed height, so the column cannot
#     grow. With the detail line in here it could: the messages run long
#     ("bus only reached 14.00 V with the FETs on, needs at least 22 V...") and
#     a wrapped second line pushed the PWM readout down into the round
#     emergency stop in the bottom-right corner. Trimming padding would have
#     bought 20px and left the same bug waiting for a longer message.
#   * a 230px-wide column is a bad place to read a sentence anyway. The left
#     column has over 400px, which is where a sentence belongs.
#
# So: numbers in the corner, prose on the left.

a06_side = ttk.Frame(A06_f)
a06_side.pack(side=RIGHT, anchor=NE, padx=20, pady=10)

a06_dot = ttk.Label(a06_side, text="●", font=("Arial", 26, "bold"), foreground="white")
a06_dot.pack(anchor="e")

a06_state_lbl = ttk.Label(a06_side, text="NO POWER", bootstyle=SECONDARY, font=(None, 22, "bold"))
a06_state_lbl.pack(anchor="e", pady=(0, 10))

a06_v_lbl = ttk.Label(a06_side, text="Voltage:  --", bootstyle=SECONDARY, style='Sub.TLabel')
a06_v_lbl.pack(anchor="e")
a06_i_lbl = ttk.Label(a06_side, text="Current:  --", bootstyle=SECONDARY, style='Sub.TLabel')
a06_i_lbl.pack(anchor="e")
a06_w_lbl = ttk.Label(a06_side, text="Power:    --", bootstyle=SECONDARY, style='Sub.TLabel')
a06_w_lbl.pack(anchor="e")
a06_t_lbl = ttk.Label(a06_side, text="Temp:     --", bootstyle=SECONDARY, style='Sub.TLabel')
a06_t_lbl.pack(anchor="e")

# What is actually being transmitted, read back from the PWM layer rather than
# from the slider position - so a clamp, or a channel switched off underneath
# us by an emergency stop, shows up here instead of being hidden behind a
# slider that is still sitting at 1250.
a06_pwm_lbl = ttk.Label(a06_side, text="PWM TOP: off    BOT: off", bootstyle=INFO, font=(None, 17, "bold"))
a06_pwm_lbl.pack(anchor="e", pady=(10, 0))

# --- left-hand column -----------------------------------------------------
# Built here rather than with the buttons at the bottom of the file because the
# status detail label belongs to it and the refresh loop needs that label to
# exist. The buttons and sliders pack into a06_main further down, after their
# handlers have been defined - pack order inside a frame is just the order the
# pack calls run in, so they land underneath this.

a06_main = ttk.Frame(A06_f)
a06_main.pack(side=LEFT, fill=BOTH, expand=TRUE, padx=40)

# Title and the wiring summary share one row rather than stacking. Purely a
# height decision: this page has to fit a power row, an LED row, two sliders
# and their buttons into the 404px that A06_f gets once the Home button has
# taken the bottom strip, and two header lines cost 24px that the sliders
# needed more than the header did.
a06_head = ttk.Frame(a06_main)
a06_head.pack(anchor="w", fill=X)

a06_title = ttk.Label(a06_head, text="Cv2_A06 TESTING", bootstyle=PRIMARY, font=(None, 19, "bold"))
a06_title.pack(side=LEFT, anchor="s")

a06_subtitle = ttk.Label(
    a06_head,
    text=f"TOP = GPIO{Manual_PWM_Test.PWM_TOP}   BOT = GPIO{Manual_PWM_Test.PWM_BOT}"
         f"   {Manual_PWM_Test.PWM_FREQ_HZ} Hz frames",
    bootstyle=SECONDARY, font=(None, 10),
)
a06_subtitle.pack(side=LEFT, anchor="s", padx=(14, 0), pady=(0, 3))

# The status message: what is happening, or why we refused.
#
# It lives in a frame with pack_propagate(False), which is the point of the
# extra frame. The label wraps, so the messages decide its height - and the
# longest of them ("bus only reached 14.00 V with the FETs on, needs at least
# 22 V. Check the battery, the fuse and the FET wiring") runs to three lines,
# which would push the bottom slider off the page the moment a power-on failed.
# Freezing the frame's height means a long message is bounded instead of being
# allowed to rearrange the controls underneath it.
#
# Measured, not guessed: the longest message this page produces is 110
# characters and asks for 40px at font 12 with this wrap width, so the reserve
# is set above that. Too small a reserve does not rearrange the page any more -
# it silently clips the end of the sentence instead, which on a FAULT is the
# half that tells you what to go and check. The corner dot carries the colour
# either way.
A06_DETAIL_H = 38
a06_detail_box = ttk.Frame(a06_main, height=A06_DETAIL_H)
a06_detail_box.pack(anchor="w", fill=X, pady=(0, 1))
a06_detail_box.pack_propagate(False)

a06_detail_lbl = ttk.Label(a06_detail_box, text="press Power On", bootstyle=INFO,
                           font=(None, 11), wraplength=430, justify="left")
a06_detail_lbl.pack(anchor="w")
#####*****END CHANGES*****#####

# --- SCREENS ---

def home():
    global mag_after_id, lidar_after_id, batt_after_id, pwr_after_id
    global propv2_after_id, propv2_idle_watch                #####*****CHANGES*****#####
    global a06_after_id, a06_idle_watch                      #####*****CHANGES*****#####

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

    #####*****CHANGES*****#####
    # Cv2_A06 page teardown, and it has to come BEFORE the session power-off
    # below, not after. Both pages take power through Hobbywing_Prop_Test's
    # session, and session_power_off() closes the gpiochip - once it has run,
    # Precharge.h is None and Manual_PWM_Test can no longer switch its own
    # frames off, because there is no handle left to write to.
    #
    # Stopping the frames first and the power second is the same ordering the
    # session teardown itself uses, and for the same reason: the signal should
    # never outlive the thing that was meant to be controlling it.
    #
    # release() aborts a running spin and switches both channels off, so no
    # navigation away from this page can leave throttle being transmitted.
    a06_stop.set()
    a06_idle_watch = False
    if a06_after_id is not None:
        root.after_cancel(a06_after_id)
        a06_after_id = None
    Manual_PWM_Test.release()
    a06_reset_sliders()

    # Stop the loom scan loop. It opens and closes gpiochip 4 on every pass, so
    # leaving it running after the page is gone would have it fighting whatever
    # the next page claims.
    loom_stop_test()
    #####*****END CHANGES*****#####

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

    #####*****CHANGES*****##### PropV2_f and A06_f added to the teardown list
    for f in [Lidar_f, Mag_f, Switch_plate_f, loom_f, Body_f, Volt_f, SBUS_f, SBUS_f_INF, Eth_f, Arm_f, PropV2_f, A06_f]:
        f.pack_forget()
    main.pack(fill=BOTH, expand=TRUE)
    root.update()

def arm():
    global batt_after_id
    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    Arm_f.pack(fill=BOTH, expand=TRUE)
    lpwm_status.config(text="PWM1: --   PWM2: --")
    arm_reason.config(text="press POWER ON", bootstyle=SECONDARY)   #####*****CHANGES*****#####
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


#####*****CHANGES*****#####
# The battery monitor is on the OUTPUT of the MOSFETs, so with them open it
# reads roughly nothing. That makes a pre-flight voltage check impossible -
# there is nothing on the shunt until the FETs conduct - but it does mean the
# reading is a direct answer to "is the rig de-energised?", which is what this
# readout wants.
def propv2_idle_readout(volts):
    """
    State for the unpowered page, decided by what the shunt actually reads.

    SAFE is an assertion about the hardware, so it is only made when there is a
    reading to back it up:

      * no reading      -> FAULT. The INA228 is not answering, so nothing else
                           on this page can be trusted either. Almost always
                           I2C wiring or the wrong address.
      * bus still up    -> FAULT. FETs open, yet there is voltage on their
                           output: residual charge in the ESC caps, a FET that
                           is not opening, or a feed wired past the switch.
      * near zero       -> SAFE, with the measured value shown so the operator
                           can see it is a measurement and not an assumption.
    """
    if volts is None:
        return "FAULT", "no INA228 reading - check the I2C wiring"

    if volts > Precharge.BUS_DEAD_MAX_V:
        return "FAULT", f"bus still at {volts:.2f} V with the FETs off - do not touch"

    note = f"{propv2_idle_note} - " if propv2_idle_note else ""
    return "SAFE", f"{note}bus {volts:.2f} V - press Power On"
#####*****END CHANGES*****#####


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
    PV2_PRECHARGE.config(state="normal", text="Power On (FET)")
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
    PV2_PRECHARGE.config(state="disabled", text="Powered")
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
    set_propv2_state("PRECHARGING", "checking input voltage...")
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
                #####*****CHANGES*****#####
                # Keep the reason pinned instead of handing the corner back to
                # the idle readout. The readout now reports the dead bus, which
                # says nothing about WHY the power-on was refused, and it
                # repaints at 10 Hz - so the message was being wiped before
                # anyone could read it. Cleared on the next Power On or on
                # re-entering the page, same as a guard trip. The live bus
                # voltage is still on screen in the Voltage label either way.
                global propv2_idle_watch, propv2_idle_note
                propv2_idle_watch = False
                propv2_idle_note = ""
                set_propv2_state("FAULT", msg)
                propv2_buttons_idle()
                #####*****END CHANGES*****#####

            propv2_post(failed)

    threading.Thread(target=worker, daemon=True).start()


def propv2_power_off():
    """
    Button: normal end-of-test power-down. LIVE -> SAFE.

    The counterpart to Power On, and the one to use when the test is
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
        set_propv2_state("FAULT", "power on before using the LED")
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
        set_propv2_state("FAULT", "power on first")
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


#####*****CHANGES*****#####
# ==========================================================================
# Cv2_A06 Testing page - behaviour
# ==========================================================================
#
# What this page is: manual throttle. Two sliders you can command by hand, and
# two canned 3-second nudges for calling the direction of rotation. No
# sequence, no pass/fail - see Subcodes/Manual_PWM_Test.py.
#
# Division of labour, same as the Prop TEST V2 page:
#
#   * Hobbywing_Prop_Test owns POWER and TELEMETRY. session_power_up() closes
#     the FET and checks the bus came up, and its Telemetry thread is the only
#     thing on the whole GUI that reads the INA228 (Batt_monitor shares one
#     SMBus object, so two readers would race). Its over-current /
#     under-voltage guards are armed by that same call, so they protect this
#     page too without anything here having to arm them.
#   * Manual_PWM_Test owns the THROTTLE FRAMES on this page.
#   * update_a06() runs on the Tk thread and only paints labels.
#   * a timed spin runs in a worker thread, because it blocks for 3 s and the
#     event loop has to stay live for the emergency stop. Workers never touch
#     widgets - they hand a callable to a06_post().
#
# ---------------------------------------------------------------------------
# THE INTERLOCK, which is the part worth reading
# ---------------------------------------------------------------------------
# The sliders and the Spin buttons command the same two ESCs, so exactly one of
# them may be in charge at a time. Rather than scatter enable/disable calls
# through every handler - which is how this kind of thing ends up with a state
# nobody tested - every handler just changes the underlying facts and then
# calls a06_refresh_controls(), which recomputes all six controls from scratch:
#
#   a spin is running     -> both sliders disabled; the active channel's button
#                            becomes CANCEL; the other channel's button is
#                            disabled (two workers on two ESCs is exactly what
#                            this prevents)
#   a slider is off rest  -> that channel's button becomes STOP, which resets
#                            the slider and the frames to 0 us; the OTHER
#                            channel's Spin button is disabled, because an
#                            automatic test while manual throttle is applied
#                            anywhere is the conflict we are avoiding
#   nothing commanded     -> both Spin buttons live, both sliders live
#   not powered           -> everything but Power On is dead
#
# There is no state in which a slider and a Spin button can both act, and
# there is nothing to get out of step because nothing is remembered: the
# function reads the real slider positions and the real worker state every
# time it runs.

#####*****CHANGES*****#####
# Same colour language as the Prop V2 page, plus two states that only exist
# here because only this page arms the ESCs as a separate operator step:
#   ARMING - in the US_ARM hold, same yellow as any other transition
#   ARMED  - frames live at idle, ESCs quiet and ready, nothing turning
A06_COLOURS = dict(PROPV2_COLOURS)
A06_COLOURS["ARMING"] = "yellow"
A06_COLOURS["ARMED"] = "cyan"
#####*****END CHANGES*****#####


def a06_post(fn):
    """Queue a UI update from a worker thread. See propv2_post()."""
    a06_ui_queue.put(fn)


def cv2_a06():
    """Enter the Cv2_A06 Testing page."""
    global a06_fault_latched, a06_idle_watch, a06_idle_note, a06_running

    main.pack_forget()
    home_b.pack(side=BOTTOM, anchor=SW, padx=20, pady=20)
    A06_f.pack(fill=BOTH, expand=TRUE)

    a06_fault_latched = False
    a06_running = False

    # Drop anything a previous visit left queued, so a stale callback cannot
    # repaint the page we are about to set up.
    while not a06_ui_queue.empty():
        try:
            a06_ui_queue.get_nowait()
        except queue.Empty:
            break

    # Open the gpiochip and force a known-safe state. No power yet - that is
    # the operator's first button. The LED line is claimed by
    # session_power_up(), so there is exactly one place that does it.
    Precharge.INITIALIZE_SYSTEM()
    Precharge.CLOSE_FET()

    # Sliders back to rest and frames off before anything else, in case a
    # previous visit left them somewhere. Done while unpowered, so this cannot
    # command anything.
    a06_stop.clear()
    Manual_PWM_Test.clear_abort()
    a06_reset_sliders()

    # Start sampling straight away so SAFE is backed by a reading rather than
    # an assumption - the bus should read ~0 V with the FETs open, and a bus
    # that does not is something the operator needs to know before touching
    # the rig. Same reasoning as the Prop V2 page.
    a06_idle_note = ""
    a06_idle_watch = True
    Hobbywing_Prop_Test.session_clear_fault()
    Hobbywing_Prop_Test.prune_logs()
    Hobbywing_Prop_Test.session_start_monitor(quiet=True)

    set_a06_state("SAFE", "reading bus...")
    a06_refresh_controls()

    # root.update() rather than update_idletasks(), and the monitor started on
    # a delay: update_a06() stops itself when the page is not viewable, so if
    # it ran before the frame was mapped it would kill its own refresh loop on
    # the first tick. Same pattern as arm() and prop_v2().
    root.update()
    root.after(100, start_a06_monitor)


def start_a06_monitor():
    global a06_after_id
    if a06_after_id is None:
        update_a06()


def set_a06_state(state, detail=""):
    """Paint the status corner. Tk thread only."""
    global a06_state
    a06_state = state
    a06_dot.config(foreground=A06_COLOURS.get(state, "white"))
    a06_state_lbl.config(text=state)
    a06_detail_lbl.config(text=detail)


def a06_idle_readout(volts):
    """
    State for the unpowered page, decided by what the shunt actually reads.

    Identical reasoning to propv2_idle_readout(): the battery monitor is on the
    OUTPUT of the MOSFETs, so with them open it reads roughly nothing - which
    makes the reading a direct answer to "is this rig de-energised?".
    """
    if volts is None:
        return "FAULT", "no INA228 reading - check the I2C wiring"

    if volts > Precharge.BUS_DEAD_MAX_V:
        return "FAULT", f"bus still at {volts:.2f} V with the FETs off - do not touch"

    note = f"{a06_idle_note} - " if a06_idle_note else ""
    return "SAFE", f"{note}bus {volts:.2f} V - press Power On"


def update_a06():
    """
    Refresh the labels at 10 Hz. Tk thread.

    Hobbywing_Prop_Test.get_state() just copies a dict under a lock, and
    Manual_PWM_Test.state() does the same - no I2C and no blocking in either,
    so this is safe to run here.
    """
    global a06_after_id, a06_fault_latched

    if not A06_f.winfo_viewable():
        a06_after_id = None
        return

    # Apply whatever the worker threads handed over since the last tick.
    while True:
        try:
            fn = a06_ui_queue.get_nowait()
        except queue.Empty:
            break
        try:
            fn()
        except Exception as e:
            print(f"[A06 UI ERROR] {e}")

    try:
        snap = Hobbywing_Prop_Test.get_state()       # volts / amps / temp / aborts
        manual = Manual_PWM_Test.state()             # what is actually going out

        V, I, T = snap["volts"], snap["amps"], snap["temp_c"]

        a06_v_lbl.config(text=f"Voltage:  {V:.2f} V" if V is not None else "Voltage:  --")
        a06_i_lbl.config(text=f"Current:  {I:.2f} A" if I is not None else "Current:  --")
        a06_w_lbl.config(
            text=f"Power:    {V * I:.0f} W" if (V is not None and I is not None) else "Power:    --"
        )
        a06_t_lbl.config(text=f"Temp:     {T:.1f} C" if T is not None else "Temp:     --")

        # "off" means no frames at all, which is the ESC-beeping condition - a
        # genuinely different state from 1000 us, so it is shown as such.
        top = f"{manual['top_us']} us" if manual["top_us"] is not None else "off"
        bot = f"{manual['bot_us']} us" if manual["bot_us"] is not None else "off"
        a06_pwm_lbl.config(text=f"PWM TOP: {top}    BOT: {bot}")

        # The per-channel readouts beside the Spin buttons, repainted from the
        # SAME source as the corner readout above. This is what makes them
        # follow the canned nudge as well as the sliders: the slider handler
        # paints them too, for instant feedback mid-drag, but it is only ever
        # painting what this loop would paint 100ms later anyway. One source of
        # truth - the pulse width actually going out - and no way for the two
        # readouts on screen to disagree.
        for channel in ("top", "bot"):
            a06_paint_value(channel, manual[f"{channel}_us"],
                            auto=(a06_running and a06_spin_channel == channel))

        if a06_idle_watch:
            # Unpowered: the corner tracks the live reading, so SAFE keeps
            # being re-confirmed rather than asserted once on page entry.
            state, detail = a06_idle_readout(V)
            set_a06_state(state, detail)

        elif Hobbywing_Prop_Test.session_live():
            # Powered. The detail line is derived here, at 10 Hz, rather than
            # being pushed from each handler: it is a description of what the
            # hardware is doing right now, and deriving it from the hardware
            # means it cannot drift out of step with it.
            #####*****CHANGES*****#####
            # Arming is now part of the ladder: powered -> armed -> driving.
            # The ARMING branch is left to the handler, which owns the status
            # for the length of the hold.
            if a06_arming:
                pass
            elif a06_running and a06_spin_channel is not None:
                set_a06_state("RUNNING",
                              f"{a06_spin_channel.upper()} spin {Manual_PWM_Test.SPIN_US} us"
                              f" - {a06_spin_remaining:.1f}s left")
            elif not manual["armed"]:
                set_a06_state("LIVE", "no signal - ESCs beep 1/s - press Init PWM")
            elif any((manual[f"{n}_us"] or 0) > Manual_PWM_Test.SLIDER_MIN_US
                     for n in ("top", "bot")):
                driving = " ".join(
                    f"{n.upper()} {manual[f'{n}_us']} us" for n in ("top", "bot")
                    if (manual[f"{n}_us"] or 0) > Manual_PWM_Test.SLIDER_MIN_US)
                set_a06_state("RUNNING", f"manual: {driving} - press STOP for idle")
            else:
                set_a06_state("ARMED",
                              f"armed, idling at {Manual_PWM_Test.SLIDER_MIN_US} us"
                              f" - ESCs quiet and ready")
            #####*****END CHANGES*****#####

        # A guard trip happens on the telemetry thread, which can only flag it
        # - it cannot cut power or touch widgets. So the Tk thread picks it up
        # here and escalates to a full emergency stop. Latched so it fires once
        # per power-up.
        reason = snap["abort_reason"]
        if (reason and not a06_fault_latched
                and ("over-current" in reason or "under-voltage" in reason)):
            a06_fault_latched = True
            print(f"[A06] guard tripped: {reason}")
            a06_estop(detail=reason)

    except Exception as e:
        a06_detail_lbl.config(text=f"telemetry error: {e}")

    finally:
        a06_after_id = root.after(100, update_a06)


# --- sliders ---------------------------------------------------------------

def a06_slider(channel):
    return A06_TOP_SLIDER if channel == "top" else A06_BOT_SLIDER


def a06_value_lbl(channel):
    return A06_TOP_VALUE if channel == "top" else A06_BOT_VALUE


def a06_spin_btn(channel):
    return A06_TOP_SPIN if channel == "top" else A06_BOT_SPIN


def a06_slider_us(channel):
    """Where the slider physically is, as an int."""
    return int(round(float(a06_slider(channel).get())))


def a06_paint_value(channel, us, auto=False):
    """
    The number beside that channel's Spin button.

    It reports THE PULSE WIDTH BEING TRANSMITTED, not the slider position. That
    distinction is the whole reason it is also repainted from update_a06():
    during a canned nudge the slider stays at rest while the channel is being
    driven at SPIN_US, and a readout tied to the slider would sit there saying
    OFF with a motor turning in front of it.

    `us` is therefore allowed to be None - that is what the PWM layer reports
    when a channel has no waveform at all, and it reads the same as the resting
    position: OFF (0 us), not "1000 us". See the comment on
    Manual_PWM_Test.SLIDER_MIN_US for why the bottom of the travel is mapped to
    off rather than to the ESC's disarm value.

    `auto` colours it differently when the value is coming from the canned
    nudge rather than from the slider, so "the slider is doing this" and "the
    automatic test is doing this" are not the same shade of blue.
    """
    #####*****CHANGES*****#####
    # Three states now, not two. "no frames" and "idle" used to read the same
    # because the resting position WAS no frames - and that was the bug: an ESC
    # with no signal is disarmed and will refuse the next throttle command.
    # They are different things and the readout has to say which one it is,
    # because one of them beeps at you and the other is ready to go.
    if us is None:
        a06_value_lbl(channel).config(text="OFF  (0 us)", bootstyle=SECONDARY)
    elif us <= Manual_PWM_Test.SLIDER_MIN_US:
        a06_value_lbl(channel).config(text=f"{us} us  (idle)", bootstyle=SECONDARY)
    else:
        a06_value_lbl(channel).config(text=f"{us} us",
                                      bootstyle=WARNING if auto else INFO)
    #####*****END CHANGES*****#####


def a06_set_slider(channel, us):
    """
    Move a slider from code.

    The echo guard is not optional. ttk.Scale fires its `command` callback for
    a programmatic .set() exactly as it does for a drag, so without it this
    would re-enter a06_slider_moved() and command the PWM again - which would
    make "reset the slider to 0" command 0 and then immediately re-command
    whatever rounding left behind.
    """
    global a06_slider_echo
    a06_slider_echo = True
    try:
        a06_slider(channel).set(us)
    finally:
        a06_slider_echo = False
    #####*****CHANGES*****#####
    # Drop any drag value still waiting to be flushed for this channel. Without
    # this, a reset could be undone a few milliseconds later by the last
    # position the finger was at before it let go.
    a06_slider_pending.pop(channel, None)
    #####*****END CHANGES*****#####
    a06_paint_value(channel, us)


def a06_reset_sliders():
    """Both sliders back to rest, both readouts to OFF. Commands nothing."""
    for channel in ("top", "bot"):
        a06_set_slider(channel, Manual_PWM_Test.SLIDER_MIN_US)
        a06_hot[channel] = False


def a06_slider_moved(channel, raw):
    """
    The operator dragged a slider.

    Fires once per motion event, so it does the absolute minimum: paint the
    label and remember where the finger is. The hardware write is handed to
    a06_slider_flush() on a timer - see the rate-limiting note up with
    a06_slider_pending for why calling lgpio from here made the slider crawl.
    """
    global a06_slider_flush_id

    if a06_slider_echo:
        return                      # our own .set(), not a drag

    us = int(round(float(raw)))
    a06_paint_value(channel, us)

    # All three of these should be unreachable - the slider is disabled in each
    # case - but a disabled widget is a UI promise, not a hardware one, and the
    # thing on the other end of it is a motor.
    if not Hobbywing_Prop_Test.session_live() or not Manual_PWM_Test.is_armed():
        a06_set_slider(channel, Manual_PWM_Test.SLIDER_MIN_US)
        return
    if a06_running or a06_arming:
        a06_set_slider(channel, Manual_PWM_Test.SLIDER_MIN_US)
        return

    a06_slider_pending[channel] = us
    if a06_slider_flush_id is None:
        a06_slider_flush_id = root.after(A06_SLIDER_FLUSH_MS, a06_slider_flush)


def a06_slider_flush():
    """
    Push the latest slider positions to the hardware. Tk thread, on a timer.

    Only the LAST value per channel is sent, however many motion events piled
    up in the interval - which is the whole point. Intermediate positions of a
    finger are not throttle settings anybody asked for, and skipping them is
    what keeps the widget tracking the drag.
    """
    global a06_slider_flush_id

    a06_slider_flush_id = None
    if not a06_slider_pending:
        return

    pending = dict(a06_slider_pending)
    a06_slider_pending.clear()

    changed = False
    for channel, us in pending.items():
        try:
            sent = Manual_PWM_Test.set_channel(channel, us)
        except Exception as e:
            print(f"[A06 SLIDER ERROR] {e}")
            a06_set_slider(channel, Manual_PWM_Test.SLIDER_MIN_US)
            set_a06_state("FAULT", str(e))
            a06_refresh_controls()
            return

        hot = sent is not None and sent > Manual_PWM_Test.SLIDER_MIN_US
        if hot != a06_hot[channel]:
            # Crossed between idle and commanding throttle: the Spin buttons
            # change meaning, so the controls need recomputing. This is the
            # only time they do.
            a06_hot[channel] = hot
            changed = True

    if changed:
        a06_refresh_controls()


# --- control enable/disable ------------------------------------------------
# The emergency stop is never disabled. That is the whole point of it.

def a06_refresh_controls():
    """
    Recompute every control on the page from the real current state.

    Single source of truth for the interlock described at the top of this
    section. Reads the actual slider positions and the actual worker state
    rather than trusting a flag someone remembered to set, so there is no way
    for the controls and the hardware to disagree.
    """
    live = Hobbywing_Prop_Test.session_live()
    #####*****CHANGES*****#####
    # `armed` is now a third gate alongside `live`. The ESCs need the US_ARM
    # hold before they will accept throttle at all, so every throttle control
    # stays locked until arming has happened - which is also what stops the
    # first press of a Spin button getting the fast refusal beep instead of a
    # turning motor.
    armed = Manual_PWM_Test.is_armed()
    arming = a06_arming
    spinning = a06_running
    hot = {c: (live and armed and a06_slider_us(c) > Manual_PWM_Test.SLIDER_MIN_US)
           for c in ("top", "bot")}
    any_hot = hot["top"] or hot["bot"]
    busy = spinning or arming or any_hot

    # --- power ---
    A06_PWR_ON.config(state="normal" if not live else "disabled",
                      text="Power On" if not live else "Powered")
    A06_PWR_ON.configure(style="A06SmallOn.TButton" if live else "A06Small.TButton")

    # Powering off is blocked while anything is commanded. Cutting power to a
    # spinning motor is the emergency case, not the normal one, and the round
    # red button in the corner is the one for that - it is the only control
    # here that is never disabled. The normal route is STOP first, then
    # Power Off, which drops the throttle before the rail.
    A06_PWR_OFF.config(state="normal" if (live and not busy) else "disabled")

    # --- initialise / disarm the PWM ---
    # Reads as the next step after Power On, which is why it sits in that row:
    # Power On -> Init PWM -> drive -> Disarm -> Power Off, left to right in
    # the order they get pressed.
    if arming:
        A06_ARM.config(state="disabled", text="arming...")
        A06_ARM.configure(style="A06Small.TButton")
    elif not armed:
        A06_ARM.config(state="normal" if live else "disabled", text="Init PWM")
        A06_ARM.configure(style="A06Small.TButton")
    else:
        # Disarming mid-throttle would drop the signal with the motor turning,
        # so it waits for idle - the corner stop is there for the other case.
        A06_ARM.config(state="normal" if not (spinning or any_hot) else "disabled",
                       text="Disarm")
        A06_ARM.configure(style="A06SmallOn.TButton")
    #####*****END CHANGES*****#####

    # --- LED ---
    # Available whenever the bus is live, including while a motor is turning.
    # Deliberately looser than the Prop V2 page, which locks everything during
    # a phase: the LED is a lamp on the same rail, it cannot interact with the
    # throttle, and wanting to check it while something spins is reasonable.
    A06_LED.config(state="normal" if live else "disabled")
    A06_LED.configure(style="A06SmallOn.TButton" if A06_LED.cget("text") == "Turn LED Off"
                      else "A06Small.TButton")

    # --- per channel: the slider and its Spin/STOP/CANCEL button ---
    for channel in ("top", "bot"):
        other = "bot" if channel == "top" else "top"
        slider = a06_slider(channel)
        btn = a06_spin_btn(channel)
        name = channel.upper()

        # A slider may be dragged only when the bus is live, the ESCs are
        # armed, and no timed spin is running. The other channel being manually
        # hot does NOT lock this slider - running both by hand is a legitimate
        # thing to want, and neither of them can start an automatic test while
        # they are up.
        slider.config(state="normal" if (live and armed and not spinning and not arming)
                      else "disabled")

        if spinning and a06_spin_channel == channel:
            # This channel's nudge is the one running: its button becomes the
            # way to cut it short.
            btn.config(state="normal", text=f"{name} CANCEL")
            btn.configure(style="A06Busy.TButton")

        elif spinning:
            # The other channel's nudge is running. No second worker.
            btn.config(state="disabled", text=f"{name} Spin")
            btn.configure(style="A06Spin.TButton")

        elif hot[channel]:
            # This slider is commanding throttle, so the button's job changes
            # from "start the canned nudge" to "put this channel back to 0".
            btn.config(state="normal", text=f"{name} STOP")
            btn.configure(style="A06Stop.TButton")

        elif hot[other]:
            # Manual throttle applied elsewhere: no automatic test may start.
            btn.config(state="disabled", text=f"{name} Spin")
            btn.configure(style="A06Spin.TButton")

        else:
            #####*****CHANGES*****#####
            # Needs `armed`, not just `live`. Offering this button to an
            # unarmed ESC is what produced the fast refusal beep on the first
            # press - the button looked available and the hardware disagreed.
            btn.config(state="normal" if (live and armed and not arming) else "disabled",
                       text=f"{name} Spin")
            btn.configure(style="A06Spin.TButton")
            #####*****END CHANGES*****#####


# --- handlers --------------------------------------------------------------

def a06_power_on():
    """
    Close the FET and confirm the bus came up. No throttle frames.

    Runs in a worker because session_power_up() waits for the bus to settle and
    then samples it, and the window must not freeze while it does.

    Straight through to Hobbywing_Prop_Test rather than reimplemented: one
    power-up path, one place where the ordering (close FET -> settle -> measure
    -> open again if it did not come up) has to be right.
    """
    global a06_fault_latched, a06_idle_watch, a06_idle_note

    if Hobbywing_Prop_Test.session_live():
        return

    a06_fault_latched = False
    a06_idle_watch = False          # the handler owns the status from here on
    a06_idle_note = ""
    a06_stop.clear()
    Manual_PWM_Test.clear_abort()
    set_a06_state("PRECHARGING", "closing FET, checking bus voltage...")
    A06_PWR_ON.config(state="disabled")

    def worker():
        try:
            csv_path = Hobbywing_Prop_Test.session_power_up(guards_enabled=True, quiet=True)

            def done():
                # Claim the two throttle lines on the handle that is now open,
                # and make sure both are switched off. Re-claiming matters
                # after a stop/restart cycle: an emergency stop closes the
                # gpiochip, so any claim from before it died with the handle.
                try:
                    Manual_PWM_Test.claim()
                    Manual_PWM_Test.all_off()
                except Exception as e:
                    print(f"[A06 CLAIM ERROR] {e}")

                a06_reset_sliders()
                set_a06_state("LIVE", "no signal - ESCs should beep 1/s")
                a06_refresh_controls()
                print(f"[A06] logging to {csv_path}")

            a06_post(done)

        except Exception as e:
            # Bind the message NOW. Python deletes the `as e` name at the end
            # of the except block, and this closure runs later off the UI
            # queue - referencing `e` in there raises, which would leave the
            # page stuck in PRECHARGING with every button locked out.
            msg = str(e)
            print(f"[A06 POWER ON ERROR] {msg}")

            def failed():
                # Pin the reason rather than handing the corner back to the
                # idle readout, which repaints at 10 Hz and would wipe it
                # before anyone could read it. Cleared on the next Power On or
                # on re-entering the page.
                global a06_idle_watch, a06_idle_note
                a06_idle_watch = False
                a06_idle_note = ""
                set_a06_state("FAULT", msg)
                a06_refresh_controls()

            a06_post(failed)

    threading.Thread(target=worker, daemon=True).start()


def a06_power_off():
    """
    Normal end-of-test power-down. LIVE -> SAFE, nothing flagged as wrong, so a
    clean session still bins its log.

    Frames go off before the rail does: release() first, then the session
    teardown, which is the same ordering _shutdown() uses internally and for
    the same reason.
    """
    global a06_fault_latched, a06_idle_watch, a06_idle_note

    if not Hobbywing_Prop_Test.session_live():
        return

    a06_stop.set()
    Manual_PWM_Test.release()

    try:
        kept = Hobbywing_Prop_Test.session_power_off()
    except Exception as e:
        print(f"[A06 POWER OFF ERROR] {e}")
        kept = None

    A06_LED.config(text="Turn LED On")
    a06_reset_sliders()

    a06_fault_latched = False
    note = "powered down"
    if kept:
        # Something earlier flagged itself, so the log survived a normal
        # shutdown. Say so, or nobody will know it is there.
        note += f", log: {os.path.basename(kept)}"
    a06_idle_note = note
    a06_idle_watch = True
    set_a06_state("SAFE", f"{note} - reading bus...")

    a06_refresh_controls()
    root.update_idletasks()


def a06_estop(detail="operator pressed STOP"):
    """
    Cut everything: frames off, LED off, FET off, gpiochip released.

    Runs synchronously on the Tk thread on purpose - an emergency stop queued
    behind a worker thread is not an emergency stop. Both
    Manual_PWM_Test.release() and session_emergency_stop() are written to be
    safe to call mid-spin and safe to call twice.
    """
    global a06_fault_latched, a06_idle_watch, a06_idle_note

    a06_stop.set()
    Manual_PWM_Test.release()       # frames die first, then the rail

    try:
        Hobbywing_Prop_Test.session_emergency_stop()
    except Exception as e:
        print(f"[A06 E-STOP ERROR] {e}")

    A06_LED.config(text="Turn LED On")
    a06_reset_sliders()

    kept = Hobbywing_Prop_Test.session_csv_path()

    if "over-current" in detail or "under-voltage" in detail:
        # A guard trip stays pinned in red with its reason until the operator
        # powers up again. Handing it to the idle readout would let it fade to
        # SAFE as the bus decays, taking the reason off the screen before
        # anyone had read it.
        a06_idle_watch = False
        log_note = f" - log: {os.path.basename(kept)}" if kept else ""
        set_a06_state("FAULT", f"{detail}{log_note}")
    else:
        a06_fault_latched = False
        a06_idle_note = detail if not kept else f"{detail}, log: {os.path.basename(kept)}"
        a06_idle_watch = True
        set_a06_state("SAFE", f"{detail} - reading bus...")

    a06_refresh_controls()
    # update_idletasks() and not update(): this can be reached from inside the
    # update_a06() after-callback when a guard trips, and a full update() there
    # would re-enter the event loop.
    root.update_idletasks()


#####*****CHANGES*****#####
def a06_arm_toggle():
    """
    Initialise the PWM, or stop it again.

    THE FIX FOR THE FIRST-PRESS BEEP. An ESC refuses to arm when the first
    signal it ever sees is above its zero point: it emits a fast error beep and
    will not turn. The page used to jump straight from no frames to 1200 us, so
    the first press of a Spin button always got that refusal and only the
    second one worked, once the ESC had been through its startup.

    So arming is now its own step the operator takes deliberately: hold
    US_ARM (1000 us) on both channels for ARM_HOLD_S, which is what the
    scripted test has always done, and only then unlock the throttle controls.
    You should hear the ESCs stop their once-a-second beep and run their arming
    tones while this is in the hold.

    Pressing it again disarms: frames off, and the 1/s beep comes back. That is
    the end-of-session state, and it is deliberately the only thing that
    switches the waveform off, because anything else doing it silently would
    leave the next command to be refused all over again.

    Arming runs in a worker because the hold blocks for two seconds and the
    emergency stop has to stay live throughout.
    """
    global a06_arming, a06_idle_watch

    if not Hobbywing_Prop_Test.session_live():
        set_a06_state("FAULT", "power on first")
        return

    if Manual_PWM_Test.is_armed():
        try:
            Manual_PWM_Test.disarm()
        except Exception as e:
            print(f"[A06 DISARM ERROR] {e}")
        a06_reset_sliders()
        set_a06_state("LIVE", "PWM off - ESCs should beep 1/s")
        a06_refresh_controls()
        return

    a06_arming = True
    a06_idle_watch = False
    a06_stop.clear()
    Manual_PWM_Test.clear_abort()
    set_a06_state("ARMING",
                  f"holding {Manual_PWM_Test.US_ARM} us for "
                  f"{Manual_PWM_Test.ARM_HOLD_S:.0f}s - ESCs should stop beeping")
    a06_refresh_controls()

    def worker():
        global a06_arming
        ok = False
        msg = ""
        try:
            ok = Manual_PWM_Test.arm()
        except Exception as e:
            msg = str(e)
            print(f"[A06 ARM ERROR] {msg}")
        finally:
            a06_arming = False

            def finish():
                # An emergency stop may have landed while we were in the hold.
                if not Hobbywing_Prop_Test.session_live():
                    a06_refresh_controls()
                    return
                a06_reset_sliders()
                if msg:
                    set_a06_state("FAULT", f"could not initialise the PWM: {msg}")
                elif not ok:
                    set_a06_state("LIVE", "arming was interrupted - frames off")
                else:
                    set_a06_state("ARMED",
                                  f"armed, idling at {Manual_PWM_Test.SLIDER_MIN_US} us"
                                  f" - sliders and Spin are live")
                a06_refresh_controls()

            a06_post(finish)

    threading.Thread(target=worker, daemon=True).start()
#####*****END CHANGES*****#####


def a06_led():
    """LED on/off. Needs the bus live - the LED runs off the switched rail."""
    if not Hobbywing_Prop_Test.session_live():
        set_a06_state("FAULT", "power on before using the LED")
        return

    if A06_LED.cget("text") == "Turn LED On":
        LED.LED_ON()
        A06_LED.config(text="Turn LED Off")
    else:
        LED.LED_OFF()
        A06_LED.config(text="Turn LED On")
    a06_refresh_controls()


def a06_spin(channel):
    """
    The per-channel button. Its job depends on what the page is doing, which is
    exactly what a06_refresh_controls() has already encoded in its text:

        "TOP Spin"    -> run the canned nudge
        "TOP STOP"    -> a slider is live; put this channel back to 0 us
        "TOP CANCEL"  -> a nudge is running; cut it short

    Reading the intent off the button rather than re-deriving it means the
    button can never do something other than what it says on it.
    """
    global a06_running, a06_spin_channel, a06_spin_remaining

    btn = a06_spin_btn(channel)
    label = btn.cget("text")

    # --- CANCEL: stop the running nudge early ---
    if label.endswith("CANCEL"):
        Manual_PWM_Test.abort()     # the worker unwinds through its own finally
        btn.config(text=f"{channel.upper()} stopping...", state="disabled")
        return

    # --- STOP: return this channel's slider and throttle to idle ---
    if label.endswith("STOP"):
        #####*****CHANGES*****#####
        # Back to SLIDER_MIN_US with the frames still running, NOT off. Below
        # the ESC's 0% point the motor stops either way, but keeping the signal
        # alive keeps the ESC armed, so the next command works immediately
        # instead of being refused. Switching the frames off is the Disarm
        # button's job now - see a06_arm_toggle().
        try:
            Manual_PWM_Test.set_channel(channel, Manual_PWM_Test.SLIDER_MIN_US)
        except Exception as e:
            print(f"[A06 STOP ERROR] {e}")
        #####*****END CHANGES*****#####
        a06_set_slider(channel, Manual_PWM_Test.SLIDER_MIN_US)
        a06_hot[channel] = False
        a06_refresh_controls()
        return

    # --- Spin: the canned nudge ---
    if a06_running:
        return
    if not Hobbywing_Prop_Test.session_live():
        set_a06_state("FAULT", "power on first")
        return
    #####*****CHANGES*****#####
    # Needs arming first, or the ESC answers with its refusal beep instead of
    # turning. The button is locked until then, so this is the hardware-side
    # copy of that interlock.
    if not Manual_PWM_Test.is_armed():
        set_a06_state("LIVE", "press Init PWM first - the ESCs are not armed")
        return

    # Refuse if a slider is already commanding throttle. The button should be
    # disabled in that case, so this is the belt-and-braces copy of the
    # interlock - the one enforced against the hardware rather than the widget.
    #
    # "> SLIDER_MIN_US", not "is not None". An armed channel ALWAYS has live
    # frames now, so "is not None" was true the moment arming finished and this
    # guard refused every single spin - the button did nothing at all. Idle and
    # "commanding throttle" are different things and this has to compare the
    # value, not merely its presence.
    manual = Manual_PWM_Test.state()
    if any((manual[f"{n}_us"] or 0) > Manual_PWM_Test.SLIDER_MIN_US
           for n in ("top", "bot")):
        set_a06_state("RUNNING", "a slider is still commanding throttle - press STOP first")
        return
    #####*****END CHANGES*****#####

    a06_running = True
    a06_spin_channel = channel
    a06_spin_remaining = Manual_PWM_Test.SPIN_HOLD_S
    a06_stop.clear()
    Manual_PWM_Test.clear_abort()
    a06_refresh_controls()          # locks the sliders and the other button

    def tick(remaining):
        # Worker thread. A plain float assignment, deliberately not a widget
        # call and not even a queued closure: update_a06() is already painting
        # at 10 Hz and will pick this up on its next tick, so pushing 10
        # closures a second through the queue would buy nothing.
        global a06_spin_remaining
        a06_spin_remaining = remaining

    def worker():
        global a06_running, a06_spin_channel
        completed = False
        try:
            completed = Manual_PWM_Test.spin(channel, on_tick=tick)
        except Exception as e:
            print(f"[A06 SPIN ERROR] {e}")
            # Keeps the log: a nudge that threw is worth looking at the trace
            # for, same rule as a failed phase on the Prop V2 page.
            Hobbywing_Prop_Test.mark_log_keep(f"{channel} manual spin raised: {e}")
        finally:
            a06_running = False
            a06_spin_channel = None

            def finish():
                # An emergency stop may have run while we were in here, in
                # which case the page is already in SAFE/FAULT and must not be
                # dragged back to LIVE.
                if not Hobbywing_Prop_Test.session_live():
                    a06_refresh_controls()
                    return
                a06_refresh_controls()
                set_a06_state("LIVE",
                              f"{channel.upper()} spin "
                              f"{'complete' if completed else 'stopped'} - frames off")

            a06_post(finish)

    threading.Thread(target=worker, daemon=True).start()


# Thin wrappers so each control has its own command and there is no
# late-binding trap on the loop variable.
def a06_spin_top():
    a06_spin("top")


def a06_spin_bot():
    a06_spin("bot")


def a06_top_slider_moved(raw):
    a06_slider_moved("top", raw)


def a06_bot_slider_moved(raw):
    a06_slider_moved("bot", raw)


def make_estop_circle(parent, command, diameter=120):
    """
    The round emergency stop, pinned to the bottom-right corner.

    A Canvas rather than a ttk.Button because ttk cannot draw a real circle,
    and place() rather than pack() so it floats over the layout in the corner
    instead of competing with the controls for vertical space - which is the
    whole reason it was moved there: these pages have to fit a 480px-high
    5-inch screen.

    relx/rely 1.0 with anchor "se" keeps it in the corner at any resolution, so
    the 5-inch and 7-inch screens both get it in the same place. Bottom-LEFT is
    taken by the Home button and the status column hugs the top-right, so this
    corner is free on both pages.

    Factored out here for the Cv2_A06 page. The Prop TEST V2 page still builds
    its own copy inline further down - left alone on purpose rather than
    refactored onto this helper, because that code is working and committed and
    there is nothing to gain from touching it.

    Returns the Canvas, already placed.
    """
    canvas = tk.Canvas(parent, width=diameter, height=diameter,
                       highlightthickness=0, bd=0,
                       bg=style.colors.bg, cursor="hand2")

    disc = canvas.create_oval(4, 4, diameter - 4, diameter - 4,
                              fill="#b02a37", outline="#ff6b7a", width=3)
    canvas.create_text(diameter / 2, diameter / 2 - 9, text="STOP",
                       fill="white", font=(None, 17, "bold"))
    canvas.create_text(diameter / 2, diameter / 2 + 13, text="EMERGENCY",
                       fill="#ffd7db", font=(None, 8, "bold"))

    def paint(fill):
        canvas.itemconfigure(disc, fill=fill)
        root.update_idletasks()     # paint before the teardown blocks

    def press(event=None):
        # Fires on PRESS, not release. Deliberate: this is the one control
        # where the fastest possible response beats guarding against a stray
        # touch, and a false trigger only powers the rig down safely. Sitting
        # alone in a corner is what keeps it from being hit by accident.
        paint("#7d1d26")
        command()

    def release(event=None):
        paint("#b02a37")

    canvas.bind("<Button-1>", press)
    canvas.bind("<ButtonRelease-1>", release)
    canvas.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor="se")
    return canvas
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
    #####*****CHANGES*****#####
    # Clear last visit's result. Without this the old matrix and its Pass!/Fail!
    # were still on screen when you walked back in, which reads as a live
    # reading for the loom you are holding now - and it is not.
    loom_stop_test()
    loom_reset_labels()
    #####*****END CHANGES*****#####


#####*****CHANGES*****#####
def loom_reset_labels():
    """Back to the "nothing measured yet" state."""
    l20.config(text="Ready to test", bootstyle=PRIMARY)
    l21.config(text="")
    lloom_note.config(text="")


def loom_start():
    """Start the repeating scan."""
    global loom_running
    if loom_running:
        return
    loom_running = True
    LOOM_START.config(state="disabled")
    LOOM_STOP.config(state="normal")
    l21.config(text="")
    loom_tick()


def loom_stop_test():
    """Stop the repeating scan. Leaves the last reading on screen."""
    global loom_after_id, loom_running
    if loom_after_id is not None:
        root.after_cancel(loom_after_id)
        loom_after_id = None
    was_running = loom_running
    loom_running = False
    LOOM_START.config(state="normal")
    LOOM_STOP.config(state="disabled")
    if was_running:
        # Say the reading is frozen. A static matrix with no note is exactly
        # what was confusing before.
        lloom_note.config(text="stopped - reading below is frozen")


def loom_once():
    """One scan, no repeat. Says so, so it cannot be mistaken for a live one."""
    loom_stop_test()
    try:
        loom_test()
        lloom_note.config(text="single reading - press Start to keep refreshing")
    except Exception as e:
        print(f"[LOOM] scan error: {e}")
        l20.config(text="ERROR", bootstyle=DANGER)
        l21.config(text="")
        lloom_note.config(text=f"scan failed: {e}")


def loom_tick():
    """
    One pass of the scan, then reschedule.

    Deliberately on the Tk thread rather than in a worker. arm_loom() is 12
    iterations with a 10ms settle each, so about 150ms - a visible hiccup but
    not a freeze, and at one pass every 2s that is well under a tenth of the
    time. Running it in a worker would buy smoothness and cost cross-thread
    widget access, which is not a trade worth making for 150ms.
    """
    global loom_after_id
    if not loom_running:
        return
    try:
        loom_test()
        lloom_note.config(text=f"running - refreshing every {LOOM_PERIOD_MS / 1000:.0f}s")
    except Exception as e:
        # A scan that throws must not kill the loop silently, and must not
        # leave a stale matrix looking current either.
        print(f"[LOOM] scan error: {e}")
        l20.config(text="ERROR", bootstyle=DANGER)
        l21.config(text="")
        lloom_note.config(text=f"scan failed: {e}")
    loom_after_id = root.after(LOOM_PERIOD_MS, loom_tick)
#####*****END CHANGES*****#####


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

#####*****CHANGES*****#####
# NO LONGER USED - kept for the PCB redesign. These drove the wait-for-bus-
# voltage loop that went with the precharge circuit; that circuit is faulty and
# disabled (see Precharge.py), so PWR_ON now does a one-shot input-voltage check
# instead. The threshold lives in Precharge.py (BUS_MIN_VOLTAGE) so
# this page and the Prop TEST V2 page cannot disagree about it.
#
# PRECHARGE_TIMEOUT = 3000
# PRECHARGE_CHECK_INTERVAL = 200
# PRECHARGE_MIN_VOLTAGE = 21.0
#
# precharge_start_time = None
# precharge_good_count = 0
#####*****END CHANGES*****#####

def arm_red():
    PWR.configure(style="ArmDanger.TButton")

def arm_reset():
    PWR.configure(style="Arm.TButton")
    for button in [PWM_INIT, SPIN_ALL, SPIN_TOP, SPIN_BOT, LED_btn, PROP]:
        button.configure(style="Arm.TButton")


#####*****CHANGES*****#####
# PWR_ON / PWR_CHECK rewritten: precharge is disabled (faulty hardware, see
# Precharge.py). What this used to do was start the precharge, then poll the bus
# voltage for up to PRECHARGE_TIMEOUT waiting for it to rise - except it also
# called OPEN_FET() on every poll, before any check ("force fet open for now
# until fix precharge issue then remove this line!!"), so the FET actually closed
# onto an unverified supply and the voltage loop only decided whether to call it
# LIVE or FAULT afterwards.
#
# That last part is almost certainly why the spin buttons stopped working: with
# the precharge circuit dead the bus never rose, the loop timed out at FAULT, and
# run_spin_toggle refuses to do anything unless current_state == "LIVE".
#
# Now: close the FETs, let the bus settle, then confirm it reached
# Precharge.BUS_MIN_VOLTAGE and open them again if it did not. The monitor is on
# the OUTPUT of the MOSFETs, so it reads nothing until they conduct - the check
# has to come after switching on. One shot, no polling loop: the old loop
# existed to watch a precharge resistor slowly charge the bus, and through a
# closed FET the bus is either up straight away or it is not coming up at all.

def read_bus_voltage(samples=4, interval=0.04):
    """
    Median of a few INA228 reads, or None if none of them answered.

    Median rather than a single read so that one I2C glitch cannot decide
    whether the FETs stay closed - in either direction. Runs on the Tk thread
    and blocks for about 160 ms, which is fine for a button press and far
    simpler than another after() state machine.
    """
    reads = []
    for _ in range(samples):
        v = Batt_monitor.read_battery_voltage()
        if v is not None:
            reads.append(v)
        time.sleep(interval)

    if not reads:
        return None
    reads.sort()
    return reads[len(reads) // 2]


def PWR_ON():
    """
    Close the FETs, then confirm the bus came up. Returns True if it went live.

    The monitor is on the OUTPUT of the MOSFETs, so there is nothing to measure
    until they conduct - the check has to happen after switching on, not before.
    If the bus does not reach Precharge.BUS_MIN_VOLTAGE the FETs are opened
    again, the state goes FAULT, and the reason is put on screen next to the
    status dot.
    """
    global pwr_after_id

    try:
        spin_stop.clear()
        Precharge.INITIALIZE_SYSTEM()
        LED.LED_OFF()
        Precharge.START_PRECHARGE()         # no-op while precharge is disabled

        set_arm_state("PRECHARGE")
        arm_reason.config(text="closing FETs...", bootstyle=INFO)
        root.update_idletasks()

        Precharge.OPEN_FET()
        Precharge.TURN_OFF_PRECHARGE()

        arm_reason.config(text="checking bus voltage...", bootstyle=INFO)
        root.update_idletasks()
        time.sleep(Precharge.BUS_SETTLE_S)  # let the bus come up before reading

        voltage = read_bus_voltage()
        ok, message = Precharge.classify_bus_voltage(voltage)

        if not ok:
            print(f"[PWR ON] opening FETs again: {message}")
            Precharge.CLOSE_FET()
            Precharge.TURN_OFF_PRECHARGE()
            pwr_after_id = None
            set_arm_state("FAULT")
            arm_reason.config(text=message, bootstyle=DANGER)
            PWR.config(text="Check Battery")
            return False

        print(f"[PWR ON] bus {message} - live")

        LED.LED_OFF()                       # bus-powered, so force it off

        Spin_test.claim_pwm_pins()

        set_arm_state("LIVE")
        arm_reason.config(text=f"bus {message}", bootstyle=SUCCESS)
        pwr_after_id = None
        return True

    except Exception as e:
        print(f"[PWR ON ERROR] {e}")

        Precharge.CLOSE_FET()
        Precharge.TURN_OFF_PRECHARGE()

        set_arm_state("FAULT")
        arm_reason.config(text=f"power on failed: {e}", bootstyle=DANGER)
        PWR.config(text="Power ERROR")
        return False


def toggle_power():
    global arm_powered

    if not arm_powered:
        # Only latch "powered" if the input check actually passed. It used to
        # latch unconditionally, which left the button reading POWER OFF after a
        # refusal - so the obvious retry did a power-off instead.
        if PWR_ON():
            arm_powered = True
            PWR.config(text="POWER OFF")
            arm_red()
        else:
            arm_powered = False
            PWR.config(text="POWER ON")
    else:
        power_off()
        arm_powered = False
        PWR.config(text="POWER ON")
        arm_reset()
#####*****END CHANGES*****#####

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
        #####*****CHANGES*****#####
        set_arm_state("FAULT")
        arm_reason.config(
            text=f"not live (state: {current_state}) - press POWER ON first",
            bootstyle=DANGER,
        )
        #####*****END CHANGES*****#####
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
        #####*****CHANGES*****#####
        set_arm_state("FAULT")
        arm_reason.config(
            text=f"not live (state: {current_state}) - press POWER ON first",
            bootstyle=DANGER,
        )
        #####*****END CHANGES*****#####
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
    arm_reason.config(text="", bootstyle=SECONDARY)   #####*****CHANGES*****#####
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

#####*****CHANGES*****#####
# ==========================================================================
# Main menu - split into two groups
# ==========================================================================
# SUB-ASSEMBLIES: parts tested on their own, before they go into a vehicle.
# BUILD TESTING:  tests run against an assembled build.
#
# Side by side rather than stacked, and that is a measurement rather than a
# preference. Stacking two groups means 8 buttons plus 2 headers in one column:
# at the old size that is 50 + 8*51 + 50 = 508px against the 480px the 5-inch
# screen has.
#
# Which it already was. Before this change the menu was ALREADY overflowing:
# "Prop TEST V2" measured 23px tall against 51px for every other button,
# because pack silently crushes the last child when it runs out of room. That
# arrived when Cv2_A06 Testing was added and took the count from 7 to 8 - a
# seventh button fitted at 457px, an eighth did not. So the group split is also
# the fix for it.
#
# Two columns of four fit comfortably: about 200px tall, against 404px of usable
# height. The buttons had to shrink from font 24 / width 30 to font 17 / width
# 22 for the pair to fit the 800px width - see "Nav.TButton" up with the other
# styles.
#
# The b1..b9 names are kept, each still pointing at the page it always did, so
# this is a re-layout and not a rewrite. Nothing outside this block refers to
# them.

menu_row = ttk.Frame(main)
menu_row.pack(expand=TRUE)      # expand with no fill = centred in `main`


def _menu_group(title):
    """
    One titled column of menu buttons.

    A heading plus a separator rather than a ttk.Labelframe: the Labelframe's
    own label font is themed and awkward to enlarge, and on a touchscreen the
    group title has to be readable at a glance. Returns the frame to pack
    buttons into - the heading and rule are already in it.
    """
    col = ttk.Frame(menu_row)
    col.pack(side=LEFT, anchor=N, padx=24)
    ttk.Label(col, text=title, style="NavHead.TLabel", bootstyle=INFO).pack(anchor=W)
    ttk.Separator(col, bootstyle=INFO).pack(fill=X, pady=(2, 10))
    return col


# --- group 1: sub-assemblies ---
menu_sub = _menu_group("SUB-ASSEMBLIES")

b1 = ttk.Button(menu_sub, text="Lidar Test", bootstyle=PRIMARY, style="Nav.TButton", width=22, command=lidar)
b1.pack(pady=3)
b4 = ttk.Button(menu_sub, text="Loom Test", bootstyle=PRIMARY, style="Nav.TButton", width=22, command=loom)
b4.pack(pady=3)
b2 = ttk.Button(menu_sub, text="Magnetometer Test", bootstyle=PRIMARY, style="Nav.TButton", width=22, command=mag)
b2.pack(pady=3)
b3 = ttk.Button(menu_sub, text="Rear Switch Plate Test", bootstyle=PRIMARY, style="Nav.TButton", width=22, command=switch_plate)
b3.pack(pady=3)

# --- group 2: build testing ---
menu_build = _menu_group("BUILD TESTING")

b5 = ttk.Button(menu_build, text="Body Test", bootstyle=PRIMARY, style="Nav.TButton", width=22, command=body)
b5.pack(pady=3)
b6 = ttk.Button(menu_build, text="Voltage Test", bootstyle=PRIMARY, style="Nav.TButton", width=22, command=volt)
b6.pack(pady=3)
b9 = ttk.Button(menu_build, text="Cv2_A06 Testing", bootstyle=PRIMARY, style="Nav.TButton", width=22, command=cv2_a06)
b9.pack(pady=3)
b8 = ttk.Button(menu_build, text="Prop TEST V2", bootstyle=PRIMARY, style="Nav.TButton", width=22, command=prop_v2)
b8.pack(pady=3)

# --- Arm Test: REMOVED from the menu --------------------------------------
# Still built, never packed, so the Arm Test page and everything behind it
# (Spin_test.py, toggle_power, INITIAL_PWM, SPIN, TOP_SPIN, BOT_SPIN,
# PROP_SPIN, update_pwm_status, the Arm_f widgets) is intact and unreachable
# rather than deleted.
#
# Built-but-not-packed rather than commented out because `arm()` and the Arm_f
# widgets below still reference each other, and update_pwm_status() runs on a
# timer from the bottom of this file. Leaving the page wired up and simply not
# offering a way into it is a one-line change with nothing to unpick - and
# packing this one line into either group is all it takes to bring it back.
#
# Its parent is `main`, not one of the groups, so nothing has to be decided
# about which group it would belong to until someone wants it back.
#
# Spin_test.py itself is untouched, as asked.
b7 = ttk.Button(main, text="Arm Test", bootstyle=PRIMARY, style="Nav.TButton", width=22, command=arm)
# b7.pack(pady=3)     <- was the menu entry. Deliberately not packed.
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
propv2_title.pack(pady=(4, 0))        #####*****CHANGES*****##### was (25, 5)

# 1. Power on. Named "precharge" in the identifiers for history - precharge
#    itself is disabled (faulty hardware); this now checks the input voltage
#    and closes the main FET. See Precharge.py.
PV2_PRECHARGE = ttk.Button(propv2_btns, text="Power On (FET)", style="PropIdle.TButton", width=26, command=propv2_precharge)
PV2_PRECHARGE.pack(expand=TRUE, pady=2)

# 2. Power off - the opposite of precharge, so it sits next to it. Normal
#    end-of-test shutdown: de-energises just as hard as the emergency stop but
#    without flagging a fault, so a clean run still bins its log.
PV2_POWEROFF = ttk.Button(propv2_btns, text="Power Off", style="PropIdle.TButton", width=26, command=propv2_power_off)
PV2_POWEROFF.pack(expand=TRUE, pady=2)

#####*****CHANGES*****#####
# 3. Emergency stop - MOVED out of this column, see the round button further
#    down. It used to live here at font 28 with padding 22 and 18px above and
#    below, about 125px of vertical space, which pushed the Pulse Test button
#    off the bottom of the 5-inch screen (it fitted on the 7-inch one).
#####*****END CHANGES*****#####

# 4. LED
PV2_LED = ttk.Button(propv2_btns, text="Turn LED On", style="PropIdle.TButton", width=26, command=propv2_led)
PV2_LED.pack(expand=TRUE, pady=2)

# 5-8. The four phases from Hobbywing_Prop_Test.SEQUENCE
PV2_TOP = ttk.Button(propv2_btns, text="TOP Test", style="PropIdle.TButton", width=26, command=propv2_top)
PV2_TOP.pack(expand=TRUE, pady=2)

PV2_BOT = ttk.Button(propv2_btns, text="BOT Test", style="PropIdle.TButton", width=26, command=propv2_bot)
PV2_BOT.pack(expand=TRUE, pady=2)

PV2_BOTH = ttk.Button(propv2_btns, text="Prop Test", style="PropIdle.TButton", width=26, command=propv2_both)
PV2_BOTH.pack(expand=TRUE, pady=2)

PV2_PULSE = ttk.Button(propv2_btns, text="Pulse Test", style="PropIdle.TButton", width=26, command=propv2_pulse)
PV2_PULSE.pack(expand=TRUE, pady=(2, 4))   #####*****CHANGES*****##### was (6, 25)

#####*****CHANGES*****#####
# --------------------------------------------------------------------------
# Emergency stop - round, pinned to the bottom-right corner
# --------------------------------------------------------------------------
# A Canvas rather than a ttk.Button because ttk cannot draw a real circle, and
# place() rather than pack() so it floats over the layout in the corner instead
# of competing with the button column for vertical space. That is the point of
# the move: the column has to fit eight items on a 480px-high 5-inch screen.
#
# relx/rely 1.0 with anchor "se" keeps it in the corner at any resolution, so
# the 5-inch and 7-inch screens both get it in the same place. Bottom-LEFT is
# taken by the Home button, and the status column hugs the top-right, so this
# corner is free.

ESTOP_D = 120           # diameter in px. 112 covered the Temp and PWM lines in Simulator
                        # on the 800x480 screen; this clears them.


def _estop_paint(fill):
    PV2_ESTOP.itemconfigure(_estop_disc, fill=fill)
    root.update_idletasks()     # paint before the teardown blocks


def _estop_press(event=None):
    """
    Fires on PRESS, not release.

    Deliberate: this is the one control where the fastest possible response
    beats guarding against a stray touch, and a false trigger only powers the
    rig down safely. Sitting in a corner on its own is what keeps it from being
    hit by accident.
    """
    _estop_paint("#7d1d26")
    propv2_estop()


def _estop_release(event=None):
    _estop_paint("#b02a37")


PV2_ESTOP = tk.Canvas(PropV2_f, width=ESTOP_D, height=ESTOP_D,
                      highlightthickness=0, bd=0,
                      bg=style.colors.bg, cursor="hand2")

_estop_disc = PV2_ESTOP.create_oval(4, 4, ESTOP_D - 4, ESTOP_D - 4,
                                    fill="#b02a37", outline="#ff6b7a", width=3)
PV2_ESTOP.create_text(ESTOP_D / 2, ESTOP_D / 2 - 9, text="STOP",
                      fill="white", font=(None, 17, "bold"))
PV2_ESTOP.create_text(ESTOP_D / 2, ESTOP_D / 2 + 13, text="EMERGENCY",
                      fill="#ffd7db", font=(None, 8, "bold"))

PV2_ESTOP.bind("<Button-1>", _estop_press)
PV2_ESTOP.bind("<ButtonRelease-1>", _estop_release)

PV2_ESTOP.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor="se")
#####*****END CHANGES*****#####

# Everything except the precharge starts locked out.
propv2_buttons_idle()
#####*****END CHANGES*****#####


#####*****CHANGES*****#####
# --------------------------------------------------------------------------
# Cv2_A06 Testing page - the controls
# --------------------------------------------------------------------------
# Created down here rather than next to the status labels because `command=` is
# evaluated immediately, so the handlers above have to already exist.
#
# Layout: status numbers in the top-right corner, title / status message /
# controls on the left, emergency stop floating in the bottom-right corner.
# a06_main, the title and the status message are built earlier, up with the
# status column; these pack underneath them.
#
# Power On and Power Off share a row - they are the two halves of one decision,
# and pairing them saves the height the sliders need on a 480px screen. The LED
# gets a row of its own: it is a different kind of action and does not belong
# in the power pair.

# --- power, and initialising the PWM ---
#####*****CHANGES*****#####
# Three buttons on this row now, in the order they get pressed:
#
#     Power On  ->  Init PWM  ->  (drive)  ->  Disarm  ->  Power Off
#
# "Init PWM" is here rather than on a line of its own because arming is part of
# the power-up sequence, and because there was no height left for a fourth row:
# A06_f gets 404px on the 5-inch screen and the controls already filled it to
# within 7px. The labels shortened from "Power On (FET)" so all three fit the
# width - the wiring summary under the title still names the FET.
#
# The LED keeps its own line, as asked.
a06_pwr_row = ttk.Frame(a06_main)
a06_pwr_row.pack(anchor="w", pady=(0, 3))

A06_PWR_ON = ttk.Button(a06_pwr_row, text="Power On", style="A06Small.TButton",
                        width=11, command=a06_power_on)
A06_PWR_ON.pack(side=LEFT, padx=(0, 6))

A06_PWR_OFF = ttk.Button(a06_pwr_row, text="Power Off", style="A06Small.TButton",
                         width=11, command=a06_power_off)
A06_PWR_OFF.pack(side=LEFT, padx=(0, 6))

A06_ARM = ttk.Button(a06_pwr_row, text="Init PWM", style="A06Small.TButton",
                     width=11, command=a06_arm_toggle)
A06_ARM.pack(side=LEFT)
#####*****END CHANGES*****#####

# --- LED, on its own line ---
A06_LED = ttk.Button(a06_main, text="Turn LED On", style="A06Small.TButton",
                     width=16, command=a06_led)
A06_LED.pack(anchor="w", pady=(0, 4))


def _a06_channel_box(parent, title):
    """
    One channel's controls: its Spin/STOP button, its slider, and its readout.

    A Labelframe so the two channels are visibly separate groups - on a small
    touchscreen it has to be obvious at a glance which slider belongs to which
    motor, because getting that wrong means spinning the one you are holding.

    The title carries the live numbers rather than hardcoded text, so changing
    Manual_PWM_Test.SLIDER_MAX_US or SPIN_US updates what is on screen as well
    as what the hardware will accept - no second place to forget.

    Putting the explanatory text in the TITLE is not decoration. It started as
    a label in the second grid column next to the readout, and on the 800x480
    screen its natural width took the column from 240px to 280px - which left
    the slider 97px of travel for a 400us band, against 321px on the 1024px
    screen. Static prose does not belong in a column that a control has to
    share. In the title it costs no width at all.
    """
    box = ttk.Labelframe(
        parent,
        text=(f"  {title}"
              f"   -   Spin = {Manual_PWM_Test.SPIN_US} us for "
              f"{Manual_PWM_Test.SPIN_HOLD_S:.0f}s"
              f"   -   Slider = OFF .. {Manual_PWM_Test.SLIDER_MAX_US} us  "),
        bootstyle=SECONDARY,
    )
    box.pack(fill=X, expand=FALSE, pady=7)
    # Column 0 takes all the spare width, column 1 keeps its natural size.
    # The slider ignores both: it spans the pair, so its travel is the full
    # width of the box rather than whatever is left after the readout.
    box.columnconfigure(0, weight=1)
    return box


def _a06_slider(parent, command):
    """
    One throttle slider.

    A classic tk.Scale rather than a ttk.Scale, and that is the only reason
    this function exists. ttk.Scale takes its trough thickness from the theme
    and measures 22px tall - fine with a mouse, not fine as a touch target on
    a 5-inch panel, and there is no supported way to thicken it. tk.Scale
    exposes `width` (the trough) and `sliderlength` (the grab handle) directly,
    so it can be made finger-sized.

    Two other things come for free and are worth having:
      * resolution=1 - values arrive as whole microseconds, so there is no
        float rounding between what the slider says and what is transmitted
      * showvalue=0 - the number lives in our own label instead, which can say
        "OFF (0 us)" at the resting position where the raw value cannot

    The cost is that tk widgets do not follow the ttk theme, so the colours are
    taken from style.colors by hand to match the rest of the page.

    from_ is the resting position AND means "frames off" - see the comment on
    Manual_PWM_Test.SLIDER_MIN_US. Mapping the bottom of the travel to off
    rather than to the ESC's 1000 us disarm value means the whole slider length
    is the band that matters, instead of 71% of it sitting below the ESC's own
    floor where nothing turns.
    """
    return tk.Scale(
        parent,
        from_=Manual_PWM_Test.SLIDER_MIN_US,
        to=Manual_PWM_Test.SLIDER_MAX_US,
        orient=HORIZONTAL,
        resolution=1,
        showvalue=0,
        length=330,
        width=34,               # trough thickness - the touch target
        sliderlength=44,        # the grab handle, wide enough to find by feel
        bd=0,
        highlightthickness=0,
        troughcolor=style.colors.dark,
        bg=style.colors.info,
        activebackground=style.colors.primary,
        command=command,
    )


A06_TOP_BOX = _a06_channel_box(a06_main, "TOP MOTOR")

A06_TOP_SPIN = ttk.Button(A06_TOP_BOX, text="TOP Spin", style="A06Spin.TButton",
                          width=14, command=a06_spin_top)
A06_TOP_SPIN.grid(row=0, column=0, sticky="w", padx=8, pady=(2, 2))

A06_TOP_VALUE = ttk.Label(A06_TOP_BOX, text="OFF  (0 us)", bootstyle=SECONDARY,
                          font=(None, 18, "bold"), width=12, anchor="e")
A06_TOP_VALUE.grid(row=0, column=1, sticky="e", padx=8, pady=(2, 2))

# columnspan=2: the slider gets the whole width of the box, not what is left
# over beside the readout. See the note in _a06_channel_box().
A06_TOP_SLIDER = _a06_slider(A06_TOP_BOX, a06_top_slider_moved)
A06_TOP_SLIDER.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(8, 14))


A06_BOT_BOX = _a06_channel_box(a06_main, "BOT MOTOR")

A06_BOT_SPIN = ttk.Button(A06_BOT_BOX, text="BOT Spin", style="A06Spin.TButton",
                          width=14, command=a06_spin_bot)
A06_BOT_SPIN.grid(row=0, column=0, sticky="w", padx=8, pady=(2, 2))

A06_BOT_VALUE = ttk.Label(A06_BOT_BOX, text="OFF  (0 us)", bootstyle=SECONDARY,
                          font=(None, 18, "bold"), width=12, anchor="e")
A06_BOT_VALUE.grid(row=0, column=1, sticky="e", padx=8, pady=(2, 2))

A06_BOT_SLIDER = _a06_slider(A06_BOT_BOX, a06_bot_slider_moved)
A06_BOT_SLIDER.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(8, 14))

# The emergency stop, in case the controls above stop responding - a hung
# worker thread, a slider that will not let go, a motor that is not doing what
# it was told. It bypasses all of it: frames off, then FET off, then the
# gpiochip released. Never disabled, under any state of this page.
A06_ESTOP = make_estop_circle(A06_f, a06_estop)

# Sliders at rest, and everything except Power On locked out.
a06_reset_sliders()
a06_refresh_controls()
#####*****END CHANGES*****#####



# Loom test page
l20 = ttk.Label(loom_f, text="Ready to test", bootstyle=PRIMARY, font=(None, 24)); l20.pack(pady=20)
l21 = ttk.Label(loom_f, text="", bootstyle=PRIMARY); l21.pack(expand=TRUE)
#####*****CHANGES*****#####
# Says whether what is on screen is live or frozen. The matrix on its own
# cannot tell you that, which is what made a leftover reading confusing.
lloom_note = ttk.Label(loom_f, text="", bootstyle=SECONDARY, font=(None, 13, "italic"))
lloom_note.pack()

# Start / Stop instead of the old single "Run Test". Start repeats the scan
# every LOOM_PERIOD_MS so you can wiggle a connector and watch the matrix
# change; Stop freezes it. "Run Test" is kept as the single-shot, because
# sometimes one reading is all you want.
loom_btns = ttk.Frame(loom_f)
loom_btns.pack(pady=25)

LOOM_START = ttk.Button(loom_btns, text="Start", bootstyle=SUCCESS, width=12, command=loom_start)
LOOM_START.pack(side=LEFT, padx=5)

LOOM_STOP = ttk.Button(loom_btns, text="Stop", bootstyle=DANGER, width=12, command=loom_stop_test)
LOOM_STOP.pack(side=LEFT, padx=5)

LOOM_ONCE = ttk.Button(loom_btns, text="Run Once", bootstyle=SECONDARY, width=12, command=loom_once)
LOOM_ONCE.pack(side=LEFT, padx=5)

# Nothing running yet, so Stop starts out dead.
LOOM_STOP.config(state="disabled")
#####*****END CHANGES*****#####

main.pack(fill=BOTH, expand=True)
update_pwm_status()
root.mainloop()