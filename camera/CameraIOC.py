import logging
import threading
import time
from pcaspy import Driver, SimpleServer, Severity, Alarm
from CameraDevice import EpicsDevice, CameraDevice
from concurrent.futures import ThreadPoolExecutor
from functools import partial

logging.basicConfig(
    level=logging.INFO,
    # format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] [%(module)s] %(filename)s:%(lineno)d - %(message)s",
    format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class IOCDriver(Driver):
    def __init__(self, device: EpicsDevice):
        Driver.__init__(self)
        self.device = device
        self._executor = ThreadPoolExecutor()
        self._process_loop = threading.Thread(target=self.run_process_loop, daemon=True)
        self.update_pvs()
        self._process_loop.start()

    def __del__(self):
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=True)

    def write(self, reason, value):
        future = self._executor.submit(self.device.set_attr, reason, value)
        future.add_done_callback(
            partial(self.write_callback, reason=reason, value=value)
        )
        return True

    def write_callback(self, future, reason, value):
        if future.result():
            self.setParam(reason, value)
            self.callbackPV(reason)
            self.updatePVs()
        else:
            self.callbackPV(reason)

    def update_pvs(self):
        logger.info(f"initializing PVs")
        for pv_base in self.device.PV_DB.keys():
            value = self.device.get_attr(pv_base)
            if value is not None:
                self.setParam(pv_base, value)
        else:
            self.updatePVs()
            logger.info(f"finished initializing PVs")

    def set_all_invalid(self):
        logger.info(f"setting all PVs to invalid")
        for pv_base in self.device.PV_DB.keys():
            self.setParamStatus(
                pv_base, severity=Severity.INVALID_ALARM, alarm=Alarm.LINK_ALARM
            )
        else:
            self.updatePVs()

    def run_process_loop(self):
        while True:
            if not self.device.check_status():
                self.set_all_invalid()
                break
            else:
                time.sleep(1)
        while True:
            logger.warning(f"camera device is not connected, trying to re-connect...")
            try:
                self.device.re_connect()
            except Exception:
                logger.exception(f"an exception occurred while trying to re-connect to camera device")
            time.sleep(3)
            if self.device.check_status():
                self.update_pvs()
                break


if __name__ == "__main__":
    server = SimpleServer()
    dev_camera = CameraDevice(device_name="", device_addr="192.168.1.200")
    dev_camera.list_pvs()
    server.createPV(dev_camera.PV_Prefix, dev_camera.PV_DB)
    driver = IOCDriver(device=dev_camera)
    while True:
        server.process(0.1)
