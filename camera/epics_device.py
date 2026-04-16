import logging
from pprint import pprint
from typing import Any, Optional
from abc import ABC, abstractmethod


logger = logging.getLogger(__name__)


class EpicsDevice(ABC):

    PV_Prefix = ""
    PV_DB = {}
    # PV_DB Example:
    # PV_DB = {
    #     "DeviceTemperature": {
    #         "type": "float",
    #         "asyn": True,
    #     },
    #     "ExposureTime": {
    #         "type": "float",
    #         "asyn": True,
    #     },
    #     "Gain": {
    #         "type": "float",
    #         "asyn": True,
    #     },
    #     "TriggerSource": {
    #         "type": "enum",
    #         "enums": ["Software", "Line0", "Line1", "Line2", "Line3"],
    #         "asyn": True,
    #     },
    # }
    # 注意事项:
    # 1. 不建议使用 scan 字段
    # 2. 建议都使用 asyn 字段

    def __init__(self, device_name, device_addr):
        self.PV_Prefix = device_name
        self.device_name = device_name
        self.device_addr = device_addr
        self.device_driver = None  # 设备实例对驱动实例的反向引用, 由驱动实例注入, 使设备实例能够调用驱动实例的方法

    def __del__(self):
        self.close()

    def list_pvs(self) -> None:
        pprint(self.PV_DB)
        # pprint(self.PV_DB, compact=True)

    @abstractmethod
    def connect(self) -> None:
        pass

    def reconnect(self) -> None:
        self.connect()

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

    @abstractmethod
    def get_attr(self, attr: str) -> Optional[Any]:
        """
        Retrieve attribute value from device.

        Args:
            attr: attribute name

        Returns:
            Retrieved attribute value.
            None if retrieve failed.
        """
        pass

    @abstractmethod
    def set_attr(self, attr: str, value: Any) -> Optional[bool]:
        """
        Set attribute value to device.

        Args:
            attr: attribute name
            value: attribute value

        Returns:
            True if set attribute value success.
            False if set failed.
            None if attribute is not supported
        """
        pass
