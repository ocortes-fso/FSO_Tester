import os
import asyncio
import pyuavcan
from pyuavcan.transport.can.media.socketcan import SocketCANMedia

async def main():
    iface = "can0"
    bitrate = 500_000

    # Setup CAN interface
    os.system(f"sudo ip link set {iface} down")
    os.system(f"sudo ip link set {iface} up type can bitrate {bitrate}")

    # Create transport
    media = SocketCANMedia(iface)
    transport = pyuavcan.transport.can.CANTransport(media)

    # Create a simple node
    node_info = pyuavcan.node.NodeInfo(name="org.example.testnode")
    node = pyuavcan.application.Node(transport, node_info)
    node.node_id = 42  # example Node ID
    await node.start()

    # Send a simple test message
    from uavcan.node import Heartbeat_1_0  # can use any message type for test
    test_msg = Heartbeat_1_0(
        uptime=123456,
        health=Heartbeat_1_0.HEALTH_OK,
        mode=Heartbeat_1_0.MODE_OPERATIONAL
    )
    await node.broadcast(test_msg)
    print("Sent DroneCAN test message")

    # Wait briefly to see if we receive any messages on the bus
    received = False
    try:
        async for transfer in node.transport.listen(Heartbeat_1_0):
            print("DroneCAN check PASS: Received message!")
            received = True
            break
    except asyncio.TimeoutError:
        pass

    if not received:
        print("DroneCAN check FAIL: No message received")

    await node.close()

asyncio.run(main())
