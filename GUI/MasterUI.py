import ttkbootstrap as ttk 
from ttkbootstrap.constants import *


#main window/home page

main = ttk.Window(themename="litera", size=[1920,1080], title="FSO Tester")  #make this full screen when its all working and add FSO logo
style = ttk.Style()
style.configure('primary.TButton', font=(None, 32, 'bold'))

#buttons for home page

b1 = ttk.Button(main, text="Lidar Test", bootstyle=PRIMARY, width=25,)
b1.pack(expand=TRUE, pady=(100,0))
b2 = ttk.Button(main, text="Magnetometer Test", bootstyle=PRIMARY, width=25,) 
b2.pack(expand=TRUE)
b3 = ttk.Button(main, text="Rear Switch Plate Test", bootstyle=PRIMARY, width=25,)
b3.pack(expand=TRUE)
b4 = ttk.Button(main, text="Arm Loom Test", bootstyle=PRIMARY, width=25,)
b4.pack(expand=TRUE) 
b5 = ttk.Button(main, text="Callisto Body Test", bootstyle=PRIMARY, width=25,)
b5.pack(expand=TRUE) 
b6 = ttk.Button(main, text="Callisto Voltage Test", bootstyle=PRIMARY, width=25,)
b6.pack(expand=TRUE, pady=(0,100)) 

#Lidar test page


#intilise main loop for UI
               
main.mainloop()    