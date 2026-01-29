from pymavlink import mavutil
import time

PORT="/dev/ttyAMA0"; BAUD=115200
NAME="AAA_OPTIONS"

m = mavutil.mavlink_connection(PORT, baud=BAUD)

hb = m.wait_heartbeat(timeout=10)
if not hb:
    raise RuntimeError("No heartbeat")
SYS = hb.get_srcSystem()
print("Heartbeat sysid:", SYS)

# collect seen components
comps=set()
t0=time.time()
while time.time()-t0 < 2:
    h = m.recv_match(type="HEARTBEAT", blocking=False)
    if h:
        comps.add(h.get_srcComponent())
    time.sleep(0.01)
comps = sorted(comps) or [hb.get_srcComponent()]
print("Seen components:", comps)

def read_from(comp):
    m.mav.param_request_read_send(SYS, comp, NAME.encode(), -1)
    t0=time.time()
    while time.time()-t0 < 1.5:
        msg = m.recv_match(type="PARAM_VALUE", blocking=False)
        if msg and msg.param_id.decode(errors="ignore").strip("\x00") == NAME:
            return msg.param_value
        time.sleep(0.02)
    return None

for comp in comps:
    print("comp", comp, "->", read_from(comp))
