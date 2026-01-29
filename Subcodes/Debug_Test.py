import time
import dronecan
from dronecan import uavcan

# MAVLink UART to FC (same link Mission Planner uses)
MAVLINK_URI = "mavcan:serial:/dev/ttyAMA0:115200"   # DroneCAN-over-MAVLink transport :contentReference[oaicite:2]{index=2}

NODE_ID = 125
PARAM = "AAA_OPTIONS"

LOCAL_NODE_ID = 120  # pick a free ID on the DroneCAN bus

def getset_param(node, name: str, integer_value: int):
    req = uavcan.protocol.param.GetSet.Request()
    req.name = name
    req.value = uavcan.protocol.param.Value(integer_value=integer_value)

    result = {"ok": False, "value": None}

    def cb(event):
        if event is None:
            result["ok"] = False
            return
        result["ok"] = True
        # response.value can contain integer_value / real_value / string_value depending on param type
        result["value"] = event.response.value

    node.request(req, NODE_ID, cb)

    # spin until callback or timeout
    t0 = time.time()
    while time.time() - t0 < 2.0 and result["ok"] is False:
        node.spin(0.1)

    return result

node_info = uavcan.protocol.GetNodeInfo.Response()
node_info.name = "org.example.debugtool"

node = dronecan.make_node(MAVLINK_URI, node_id=LOCAL_NODE_ID, node_info=node_info)  # :contentReference[oaicite:3]{index=3}

try:
    print("Setting AAA_OPTIONS=44")
    r = getset_param(node, PARAM, 44)
    print("OK:", r["ok"], "Resp:", r["value"])

    print("Press Ctrl+C to restore to 40 and exit.")
    while True:
        node.spin(0.5)

except KeyboardInterrupt:
    pass
finally:
    print("Restoring AAA_OPTIONS=40")
    r = getset_param(node, PARAM, 40)
    print("OK:", r["ok"], "Resp:", r["value"])
    node.close()
