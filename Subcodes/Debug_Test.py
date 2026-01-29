import os
os.environ["MAVLINK20"] = "1"

import time
import dronecan
from dronecan import uavcan

MAVLINK_URI = "mavcan:/dev/ttyAMA0"
NODE_ID = 125
PARAM = "AAA_OPTIONS"
LOCAL_NODE_ID = 120

def getset_param(node, name: str, integer_value: int | None):
    req = uavcan.protocol.param.GetSet.Request()
    req.name = name
    if integer_value is not None:
        req.value = uavcan.protocol.param.Value(integer_value=integer_value)

    result = {"ok": False, "value": None}

    def cb(event):
        if event:
            result["ok"] = True
            result["value"] = event.response.value

    node.request(req, NODE_ID, cb)

    t0 = time.time()
    while time.time() - t0 < 2.0 and not result["ok"]:
        node.spin(0.1)

    return result


### ADDED: Node visibility check ###
def get_node_info(node, nid):
    req = uavcan.protocol.GetNodeInfo.Request()
    got = {"ok": False}

    def cb(e):
        if e:
            got["ok"] = True
            print("NodeInfo name:", e.response.name)

    node.request(req, nid, cb)

    t0 = time.time()
    while time.time() - t0 < 2.0 and not got["ok"]:
        node.spin(0.1)

    return got["ok"]


node_info = uavcan.protocol.GetNodeInfo.Response()
node_info.name = "org.example.debugtool"

node = dronecan.make_node(
    MAVLINK_URI,
    node_id=LOCAL_NODE_ID,
    node_info=node_info,
    baudrate=115200
)

### ADDED: visibility + read test ###
print("Node125 visible:", get_node_info(node, NODE_ID))
print("Read AAA_OPTIONS:", getset_param(node, PARAM, None))

try:
    print("Setting AAA_OPTIONS = 44")
    r = getset_param(node, PARAM, 44)
    print("OK:", r["ok"], "Resp:", r["value"])

    print("Press Ctrl+C to restore to 40 and exit.")
    while True:
        node.spin(0.5)

except KeyboardInterrupt:
    pass
finally:
    print("Restoring AAA_OPTIONS = 40")
    r = getset_param(node, PARAM, 40)
    print("OK:", r["ok"], "Resp:", r["value"])
    node.close()
