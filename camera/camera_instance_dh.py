import os, sys

os.environ["EPICS_CA_MAX_ARRAY_BYTES"] = "5000000"

import logging
from pcaspy import SimpleServer
from ioc_driver import IOCDriver
from CameraDeviceDH import CameraDeviceDH


logging.basicConfig(
    level=logging.DEBUG,
    # format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] [%(module)s] %(filename)s:%(lineno)d - %(message)s",
    format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("pcaspy").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    server = SimpleServer()
    dev_camera = CameraDeviceDH(
        device_name="", device_addr="192.168.1.200", verbose=False
    )
    dev_camera.list_pvs()
    server.createPV(dev_camera.PV_Prefix, dev_camera.PV_DB)
    driver = IOCDriver(device=dev_camera)
    while True:
        server.process(0.1)
