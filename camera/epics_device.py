import threading
from pprint import pprint
from typing import Any, Optional
from abc import ABC, abstractmethod


class EpicsDevice(ABC):

    _instance = {}

    connect_lock = threading.Lock()  # 连接操作的过程锁
    is_running = False

    PV_Prefix = ""
    PV_DB = {}

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instance:
            cls._instance[cls] = super().__new__(cls)
        return cls._instance[cls]

    def __init__(self, device_name, device_addr):
        self.PV_Prefix = device_name
        self.device_name = device_name
        self.device_addr = device_addr
        self.device_driver = None  # 设备实例对驱动实例的反向引用, 由驱动实例注入, 使设备实例能够调用驱动实例的方法

    def __del__(self):
        self.close()

    def list_pvs(self) -> None:
        pprint(self.PV_DB)

    @abstractmethod
    def connect(self) -> None:
        pass

    def reconnect(self) -> None:
        self.connect()

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def handle_disconnection(self) -> None:
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
            Retrieved attribute value from hardware device.
            None if retrieve failed.
        """
        pass

    @abstractmethod
    def set_attr(self, attr: str, value: Any) -> Optional[bool]:
        """
        Set attribute value to hardware device.

        Args:
            attr: attribute name
            value: attribute value

        Returns:
            True if set attribute value success.
            False if set failed.
            None if attribute is not supported.
        """
        pass
