import ttkbootstrap as ttk 
from ttkbootstrap.constants import *
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Subcodes import Magnetometer

root = ttk.Window(themename="cyborg", size=[1920,1080], title="FSO Tester") 
style = ttk.Style()
root.state('zoomed')
style.configure('primary.TButton', font=(None, 32, 'bold'))
style.configure('Outline.TButton', font=(None, 16, 'bold'))
style.configure('secondary.TButton', font=(None, 32, 'bold'))

# Global flag to track the magnetometer loop state
mag_running = False

def home ():
   global mag_running
   mag_running = False # Reset flag when going home
   lidar_f.pack_forget()
   mag_f.pack_forget()
   switch_plate_f.pack_forget()
   arm_f.pack_forget()
   body_f.pack_forget()
   volt_f.pack_forget()
   SBUS_f.pack_forget()
   SBUS_f_INF.pack_forget()
   main.pack(fill=BOTH, expand=TRUE)
    
def lidar ():
   main.pack_forget()
   lidar_f.pack(fill=BOTH, expand=TRUE)
   
def mag ():
   global mag_running
   main.pack_forget()
   mag_f.pack(fill=BOTH, expand=TRUE) 
   if not mag_running:
       mag_running = True
       update_mag() # Start the real-time update loop
   
def switch_plate ():
   main.pack_forget()
   switch_plate_f.pack(fill=BOTH, expand=TRUE)
   
def arm ():
   main.pack_forget()
   arm_f.pack(fill=BOTH, expand=TRUE)

def body ():
   main.pack_forget()
   body_f.pack(fill=BOTH, expand=TRUE)    

def volt ():
   main.pack_forget()
   volt_f.pack(fill=BOTH, expand=TRUE)

def SBUS_INF ():
   SBUS_f.pack_forget()
   create_sliders(SBUS_f_INF)
   SBUS_f_INF.pack(fill=BOTH, expand=TRUE)
   
def SBUS ():
   main.pack_forget()
   SBUS_f.pack(fill=BOTH, expand=TRUE)

# Main window/home page
main = ttk.Frame(root) 

b1 = ttk.Button(main, text="Lidar Test", bootstyle=PRIMARY, width=30, command=lidar)
b1.pack(expand=TRUE, pady=(20,0))
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
b7 = ttk.Button(main, text="SBUS Test", bootstyle=PRIMARY, width=30, command=SBUS)
b7.pack(expand=TRUE)

home_b = ttk.Button(root, text="Home", bootstyle=(OUTLINE), command=home, width=10)
home_b.pack(side=BOTTOM, anchor=SW, padx =20, pady=20)

# Lidar test page
lidar_f = ttk.Frame(root) 

# Mag test page
mag_f = ttk.Frame(root)
# Increased font size for better visibility on 1080p screen
l1 = ttk.Label(mag_f, text="Waiting for Magnetometer...", bootstyle=PRIMARY, font=(None, 48), justify=CENTER, anchor=CENTER)
l1.pack(fill=BOTH, expand=TRUE)

def update_mag():
   global mag_running
   if not mag_running or not mag_f.winfo_viewable():
       mag_running = False
       return

   try:
       val = Magnetometer.main()
       # Display X, Y, Z, and Magnitude (B)
       l1.config(text=f"X: {val[0]} \nY: {val[1]} \nZ: {val[2]} \n|B|: {val[3]:.1f}")
   except Exception as e:
       l1.config(text=f"Mag Error: {e}", bootstyle="danger")
   
   # Schedule the next check in 100ms for smoother real-time response
   root.after(100, update_mag)

# Switch plate test page
switch_plate_f = ttk.Frame(root)

# Arm test 
arm_f = ttk.Frame(root)

# Body test
body_f = ttk.Frame(root)

# Voltage test
volt_f = ttk.Frame(root)

# SBUS
SBUS_f = ttk.Frame(root)
SB1 = ttk.Button(SBUS_f, text="Infravision SBUS (15-pin)", bootstyle=SECONDARY, width=30, command=SBUS_INF)
SB1.pack(expand=TRUE)
SB2 = ttk.Button(SBUS_f, text="Standard SBUS (9-pin)", bootstyle=SECONDARY, width=30)
SB2.pack(expand=TRUE)

# Invravision SBUS
SBUS_f_INF = ttk.Frame(root)

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

# Initialize main loop for UI
main.pack(fill=BOTH, expand=True)             
root.mainloop()