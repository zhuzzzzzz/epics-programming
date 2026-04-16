import time
import logging
import threading
import gxipy as gx
from epics_device import EpicsDevice
from PIL import Image


logger = logging.getLogger(__name__)


image_store = None


class CameraDeviceDH(EpicsDevice):
    _instance = None

    PV_Prefix = ""
    PV_DB = {
        "DeviceTemperature": {
            "type": "float",
            "asyn": True,
        },
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
        "Trigger": {
            "type": "enum",
            "enums": ["Software", "Line0", "Line1", "Line2", "Line3"],
            "asyn": True,
        },
        "IMG": {
            "type": "char",
            "asyn": True,
            "count": 1280 * 1024,
        },
        "frame-id": {
            "type": "int",
            "asyn": True,
        },
        "Width": {
            "type": "int",
            "asyn": True,
        },
        "Height": {
            "type": "int",
            "asyn": True,
        },
    }

    ATTR_READ_ALLOW_LIST = [
        "DeviceTemperature",
        "ExposureTime",
        "Gain",
        "TriggerSource",
        "Width",
        "Height",
    ]
    ATTR_WRITE_ALLOW_LIST = [
        "ExposureTime",
        "Gain",
        "TriggerSource",
    ]
    ATTR_EXEC_ALLOW_LIST = [
        "Trigger",
    ]
    ATTR_RESERVE_LIST = [
        "IMG",
        "frame-id",
    ]

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, device_name, device_addr, verbose=False):
        if not device_addr:
            return
        super().__init__(device_name, device_addr)
        #
        self.verbose = verbose  # 控制是否输出关于异常的详细日志
        self._write_lock = {
            item: threading.Lock() for item in self.ATTR_WRITE_ALLOW_LIST
        }
        #
        self.connect()

    def connect(self):
        logger.info(f'connecting to camera "{self.device_name}@{self.device_addr}"')
        if hasattr(self, "device_manager"):
            logger.debug("delete device manager")
            del self.device_manager
            time.sleep(3)
        logger.debug("create device manager")
        self.device_manager = gx.DeviceManager()
        self.device_manager.update_device_list()
        logger.info("opening camera device")
        self.camera = self.device_manager.open_device_by_ip(self.device_addr)
        self.data_stream = self.camera.data_stream[0]
        logger.info("register capture callback")
        logger.info('set "TriggerMode" to gx.GxSwitchEntry.ON')
        self.camera.TriggerMode.set(gx.GxSwitchEntry.ON)
        # self.camera.TriggerSource.set(gx.GxTriggerSourceEntry.SOFTWARE)
        self.data_stream.register_capture_callback(handle_image_CameraDeviceDH)
        logger.info("camera stream on")
        self.camera.stream_on()
        logger.info("camera device ready")

    def reconnect(self):
        self.connect()

    def is_connected(self):
        try:
            self.camera.DeviceTemperature.get()
        except Exception:
            return False
        else:
            return True

    def close(self):
        try:
            if hasattr(self, "camera"):
                logger.info("camera stream off")
                self.camera.stream_off()
            if hasattr(self, "data_stream"):
                logger.info("unregister capture callback")
                self.data_stream.unregister_capture_callback()
            if hasattr(self, "camera"):
                logger.info("closing camera device")
                self.camera.close_device()
        except Exception as e:
            if self.verbose:
                logger.exception("close camera failed")
            else:
                logger.error(f"close camera failed: {e}")
        else:
            logger.info("camera device closed")

    def get_attr(self, attr):
        val = None
        if attr in self.ATTR_READ_ALLOW_LIST:
            if hasattr(self.camera, attr):
                handler = getattr(self.camera, attr)
                try:
                    val = handler.get()
                except Exception as e:
                    if self.verbose:
                        logger.exception(f'get_attr failed for "{attr}"')
                    else:
                        logger.warning(f'get_attr failed for "{attr}": {e}')
                else:
                    if attr == "TriggerSource":
                        val = val[0]
                    return val
            else:
                logger.error(f'get_attr failed, invalid attribute "{attr}"')
        return None

    def set_attr(self, attr, value):
        if attr in self.ATTR_WRITE_ALLOW_LIST:
            if hasattr(self.camera, attr):
                if attr in self.ATTR_WRITE_ALLOW_LIST:
                    handler = getattr(self.camera, attr)
                    try:
                        handler.set(value)
                    except Exception as e:
                        if self.verbose:
                            logger.exception(
                                f'set_attr failed(set "{attr}" to {repr(value)})'
                            )
                        else:
                            logger.error(
                                f'set_attr failed(set "{attr}" to {repr(value)}): {e}'
                            )
                        return False
                    else:
                        logger.info(f'set "{attr}" to {repr(value)}')
                        return True
            else:
                logger.error(
                    f'set_attr failed: "{attr}" is not an attribute of "{self.__class__.__name__}"'
                )
                return True
        elif attr in self.ATTR_EXEC_ALLOW_LIST:
            if attr == "Trigger":
                self.trigger()
            return None
        elif attr in self.ATTR_RESERVE_LIST:
            # no read or write
            logger.warning(f'set_attr failed: "{attr}" is reserved')
            return False
        elif attr in self.ATTR_READ_ALLOW_LIST:
            # can read but can't write
            logger.warning(f'set_attr failed: "{attr}" is read-only')
            return False
        else:
            return None

    def trigger(self):
        logger.info("send software trigger command")
        try:
            self.camera.TriggerSoftware.send_command()
        except Exception as e:
            if self.verbose:
                logger.exception("trigger failed")
            else:
                logger.error(f"trigger failed: {e}")


camera_device_dh = CameraDeviceDH("", "")


def handle_image_CameraDeviceDH(raw_image):
    logger.info(
        "Frame ID: %d   Height: %d   Width: %d"
        % (raw_image.get_frame_id(), raw_image.get_height(), raw_image.get_width())
    )
    # create numpy array with data from raw image
    numpy_image = raw_image.get_numpy_array()
    if numpy_image is None:
        print("Failed to get numpy array from RawImage")
        return
    print(numpy_image)

    # show acquired image
    # img = Image.fromarray(numpy_image, "L")
    # img.show()

    if hasattr(camera_device_dh, "device_driver"):
        if hasattr(camera_device_dh.device_driver, "set_pv_value"):
            camera_device_dh.device_driver.set_pv_value(
                "frame-id", raw_image.get_frame_id()
            )
            camera_device_dh.device_driver.set_pv_value("IMG", numpy_image.flatten())


if __name__ == "__main__":
    camera = CameraDeviceDH("test", "192.168.1.200")
    camera.list_pvs()
