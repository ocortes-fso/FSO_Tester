# Send mavlink message to enter debug mode (AAA_options=44) through serial line to CAN node 125 (powerstack) and return/print messages
# Use the UART GPIOS on the RASPI5.

##### CONFIG #####
import time 
from pymavlink import mavutil
import threading
from collections import deque

PORT = "/dev/ttyAMA0"           # or /dev/serial0
BAUD = 115200 

NODE_ID = 125                   # CAN node ID
PARAM_NAME = "AAA_OPTIONS"      # Parameter to change
MODE_ON = "44"                  # Parameter value
MODE_OFF = "40"            

##### STATE #####
_mav = None
_reader_t = None
_stop = threading.Event()
_lines = deque(maxlen=500)

_target_system = None
_target_component = NODE_ID

_connected = False

##### INTERNAL FUNCTIONS #####
def _push(line: str):
    ts = time.strftime("%d/%m/%Y %H:%M:%S")
    _lines.append(f"{ts} : {line}")

def _reader_loop():
    while not _stop.is_set():
        try:
            msg = _mav.recv_match(type="STATUSTEXT", blocking=True, timeout=0.5)
            if not msg:
                continue

            txt = msg.text
            if isinstance(txt, (bytes, bytearray)):
                txt = txt.decode(errors="ignore")
            txt = txt.strip("\x00")

            _push(txt)

        except Exception as e:
            _push(f"Reader error: {e}")
            time.sleep(0.5)

def _ensure_connected() -> bool:
    global _mav, _reader_t, _target_system, _connected

    if _connected and _mav is not None:
        return True

    try:
        _mav = mavutil.mavlink_connection(PORT, baud=BAUD)
        if not _mav.wait_heartbeat(timeout=10):
            _push("No heartbeat")
            close()
            return False

        _target_system = _mav.target_system

        _stop.clear()
        _reader_t = threading.Thread(target=_reader_loop, daemon=True)
        _reader_t.start()

        _connected = True
        _push("Connected")
        return True

    except Exception as e:
        _push(f"Connect error: {e}")
        close()
        return False

def _wait_param_value(timeout_s: float = 2.0):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        msg = _mav.recv_match(type="PARAM_EXT_VALUE", blocking=False)
        if not msg:
            time.sleep(0.02)
            continue

        name = msg.param_id.decode(errors="ignore").strip("\x00")
        if name != PARAM_NAME:
            continue

        val = msg.param_value
        if isinstance(val, (bytes, bytearray)):
            val = val.decode(errors="ignore").strip("\x00")
        return str(val)
    return None

def _read_param() -> str | None:
    _mav.mav.param_ext_request_read_send(
        _target_system,
        _target_component,
        PARAM_NAME.encode("ascii"),
        -1
    )
    return _wait_param_value(timeout_s=2.0)

def _set_param(value_str: str, timeout_s: float = 5.0) -> bool:
    _mav.mav.param_ext_set_send(
        _target_system,
        _target_component,
        PARAM_NAME.encode("ascii"),
        str(value_str).encode("ascii"),
        mavutil.mavlink.MAV_PARAM_TYPE_REAL32
    )

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        msg = _mav.recv_match(type=["PARAM_EXT_ACK", "PARAM_EXT_VALUE"], blocking=True, timeout=1)
        if not msg:
            continue

        if msg.get_type() == "PARAM_EXT_ACK":
            name = msg.param_id.decode(errors="ignore").strip("\x00")
            if name == PARAM_NAME:
                return True

        if msg.get_type() == "PARAM_EXT_VALUE":
            name = msg.param_id.decode(errors="ignore").strip("\x00")
            if name == PARAM_NAME:
                val = msg.param_value
                if isinstance(val, (bytes, bytearray)):
                    val = val.decode(errors="ignore").strip("\x00")
                if str(val).strip() == str(value_str).strip():
                    return True

    return False

##### PUBLIC FUNCTIONS (API) #####
def start() -> bool:                # Call when entering the Debug page. Connects and starts reader thread if needed.
    ok = _ensure_connected()
    if ok:
        cur = _read_param()
        _push(f"{PARAM_NAME} current: {cur}")
    return ok


def set_mode_44() -> bool:          # Set AAA_OPTIONS=44 (enable debug view).
    if not _ensure_connected():
        return False
    ok = _set_param(MODE_ON)
    _push(f"{PARAM_NAME} -> {MODE_ON} ({'OK' if ok else 'FAIL'})")
    return ok


def set_mode_40() -> bool:          # Set AAA_OPTIONS=40 (restore normal).
    if not _ensure_connected():
        return False
    ok = _set_param(MODE_OFF)
    _push(f"{PARAM_NAME} -> {MODE_OFF} ({'OK' if ok else 'FAIL'})")
    return ok


def read_messages(max_lines: int = 200):  # Call from root.after loop. Returns a list of new lines since last call.
    out = []
    while _lines and len(out) < max_lines:
        out.append(_lines.popleft())
    return out


def close():                        # Call when leaving Debug page or going Home. Stops thread, closes port. Best-effort restore to 40.
    global _mav, _reader_t, _connected, _target_system

    try:
        if _mav is not None and _target_system is not None:
            _set_param(MODE_OFF, timeout_s=2.0)
    except Exception:
        pass

    _stop.set()      
    _reader_t = None
    _connected = False
    _target_system = None

    if _mav is not None:
        try:
            _mav.close()
        except Exception:
            pass
        _mav = None