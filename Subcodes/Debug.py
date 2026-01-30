import os
import asyncio
import pyuavcan
from pyuavcan.transport.can.media.socketcan import SocketCANMedia

async def main():
    os.system("sudo ip link set can0 down")
    os.system("sudo ip link set can0 up type can bitrate 500000")

    media = SocketCANMedia('can0')
    transport = pyuavcan.transport.can.CANTransport(media)

    node_info = pyuavcan.node.NodeInfo(name="org.example.testnode")
    node = pyuavcan.application.Node(transport, node_info)
    node.node_id = 42
    await node.start()

    received = False
    try:
        async for transfer in node.transport.listen(timeout=5):
            received = True
            break
    except asyncio.TimeoutError:
        pass

    if received:
        print("DroneCAN check PASS")
    else:
        print("DroneCAN check FAIL")

    await node.close()

asyncio.run(main())
