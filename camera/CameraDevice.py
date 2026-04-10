from abc import ABC, abstractmethod
import threading
import time
import gxipy as gx
import logging

logging.basicConfig(
    level=logging.INFO,
    # format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] [%(module)s] %(filename)s:%(lineno)d - %(message)s",
    format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class EpicsDevice(ABC):

    PV_Prefix = ""
    PV_DB = {}
    # Example:
    # PV_DB = {
    #     'PV_Suffix': {
    #         'PV_Attribute': 'Value',
    #     },
    # }

    def __init__(self, device_name, device_addr, timeout=3.0):
        self.PV_Prefix = device_name
        self.device_name = device_name
        self.device_addr = device_addr
        self.timeout = timeout

    def list_pvs(self):
        for pv_suffix, pv_attr in self.PV_DB.items():
            pv_name = self.PV_Prefix + pv_suffix
            print(f"{pv_name}: {pv_attr}")

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def check_status(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def get_attr(self, attr):
        pass

    @abstractmethod
    def set_attr(self, attr, value):
        pass


class CameraDevice(EpicsDevice):

    PV_Prefix = ""
    PV_DB = {
        "ExposureTime": {
            "type": "float",
            "asyn": True,
        },
        "Gain": {
            "type": "float",
            "asyn": True,
        },
        "TriggerSource": {
            "type": "enum",
            "enums": ["Software", "Line0", "Line1", "Line2", "Line3"],
            "asyn": True,
        },
    }

    ATTR_ALLOW_LIST = [
        "ExposureTime",
        "Gain",
        "TriggerSource",
    ]

    def __init__(self, device_name, device_addr, timeout=3.0):
        super().__init__(device_name, device_addr, timeout)
        self.mac_addr = None
        self.connect()
        self._write_lock = {item: threading.Lock() for item in self.ATTR_ALLOW_LIST}

    def __del__(self):
        self.close()

    def connect(self):
        logger.info("connecting to camera device")
        if hasattr(self, "device_manager"):
            del self.device_manager
            time.sleep(5)
        self.device_manager = gx.DeviceManager()
        self.device_manager.update_device_list()
        device_info_list = self.device_manager.get_device_info()
        for item in device_info_list:
            if item.get("ip", None) == self.device_addr:
                self.mac_addr = item.get("mac", None)
                break
        logger.info("opening camera device")
        self.camera = self.device_manager.open_device_by_ip(self.device_addr)
        self.data_stream = self.camera.data_stream[0]
        self.camera.stream_on()
        logger.info("camera stream on")
        logger.info("camera device ready")

    def re_connect(self):
        if self.mac_addr:
            logger.info("resetting camera device")
            self.device_manager.gige_reset_device(
                self.mac_addr, gx.GxResetDeviceModeEntry.RESET
            )
            time.sleep(1)
        self.connect()

    def is_connect(self):
        try:
            self.camera.DeviceTemperature.get()
        except Exception:
            logger.exception("an exception occurred while checking the camera status")
            return False
        return True

    def check_status(self):
        return self.is_connect()

    def close(self):
        logger.info("closing camera device")
        try:
            self.camera.stream_off()
            logger.info("camera stream off")
            logger.info("closing camera device")
            self.camera.close_device()
        except Exception:
            logger.exception("an exception occurred while closing camera")
        else:
            logger.info("camera device closed")

    def get_attr(self, attr):
        if hasattr(self.camera, attr):
            value = None
            handler = getattr(self.camera, attr)
            try:
                value = handler.get()
            except Exception:
                logger.exception(f'failed to get "{attr}"')
            else:
                if attr == "TriggerSource":
                    value = value[0]
                return value
        else:
            logger.error(f'failed to get "{attr}"')
            logger.error(f'"{attr}" is not an attribute of "{self.__class__.__name__}"')

    def set_attr(self, attr, value):
        if hasattr(self.camera, attr):
            if attr in self.ATTR_ALLOW_LIST:
                handler = getattr(self.camera, attr)
                lock = self._write_lock[attr]
                if not lock.acquire(blocking=False):
                    logger.warning(f'failed to set "{attr}" to {repr(value)}')
                    logger.warning(f'"{attr}" is currently locked by another thread')
                    return False
                try:
                    handler.set(value)
                except Exception:
                    logger.exception(f'failed to set "{attr}" to {repr(value)}')
                    return False
                else:
                    logger.info(f'set "{attr}" to {repr(value)}')
                    return True
                finally:
                    lock.release()
            else:
                logger.warning(f'failed to set "{attr}" to {repr(value)}')
                logger.warning(f'"{attr}" is not an allowed attribute')
                return False
        else:
            logger.error(f'failed to get "{attr}"')
            logger.error(f'"{attr}" is not an attribute of "{self.__class__.__name__}"')
            return True


if __name__ == "__main__":
    camera = CameraDevice("test", "192.168.1.200")
    camera.list_pvs()
