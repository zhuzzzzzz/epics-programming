import time
from epics import PV, poll

# Mapping attribute name to PV name
# "attribute_name": ("PV_name_get", ["PV_name_put"])
ATTRIBUTE_PV_DICT = {
    "ramper": ("ramper:worker_test_1",),
    "limit": ("limit:worker_test_1",),
    "ctrl": ("ctrl:worker_test_1",),
    "step": ("step:worker_test_1",),
}


class EpicsDevice:
    def __init__(
        self,
        name: str = "DefaultDevice",
        attribute_pv_dict: dict = {},
        timeout: float = 3.0,
    ):
        """
        EpicsDevice类, 基于pyepics实现的设备抽象类, 基于类对象的属性读写进行PV访问

        Args:
            name: 设备名称
            attribute_pv_dict: 存储属性及PV名称的字典. 以类属性名称为键, PV读写名称构成的元组为值, "attribute_name": ("PV_name_get", ["PV_name_put"])
            timeout: PV连接及读写操作的超时时间
        """
        self._name = name
        self._timeout = timeout
        self._pvs = {}
        for attr_name, pvname_tuple in attribute_pv_dict.items():
            if len(pvname_tuple) == 1:
                self._pvs[attr_name] = (PV(pvname_tuple[0]), PV(pvname_tuple[0]))
            elif len(pvname_tuple) == 2:
                self._pvs[attr_name] = (PV(pvname_tuple[0]), PV(pvname_tuple[1]))
            else:
                raise ValueError(
                    f'{str(self)}: Invalid PV name tuple "{pvname_tuple}".'
                )
        else:
            self.wait_for_pvs_connection()

    def __repr__(self):
        return f'EpicsDevice("{self._name}")'

    def __getattr__(self, name):
        pvs = self.__dict__.get("_pvs", {})
        if pvs and name in pvs:
            return pvs[name][0].value
        raise AttributeError(name)

    def __setattr__(self, name, value):
        pvs = self.__dict__.get("_pvs", {})
        if pvs and name in pvs:
            pvs[name][1].put(value, wait=True, timeout=self._timeout)
            return
        super().__setattr__(name, value)

    def wait_for_pvs_connection(self):
        for pv_tuple in self._pvs.values():
            for pv in pv_tuple:
                if not pv.wait_for_connection(timeout=self._timeout):
                    raise TimeoutError(
                        f'{str(self)}: Connection timeout for PV "{pv.pvname}".'
                    )

    def list_pvs(self):
        if not self._pvs:
            print("No PV available.")
        for attr_name, pv_tuple in self._pvs.items():
            read_pv = pv_tuple[0].pvname
            write_pv = pv_tuple[1].pvname
            read_value = pv_tuple[0].value
            write_value = pv_tuple[1].value
            if read_pv == write_pv:
                print(f"  {attr_name}: Read/Write -> {read_pv} [Value: {read_value}]")
            else:
                print(
                    f"  {attr_name}: Read -> {read_pv} [Value: {read_value}], "
                    f"Write -> {write_pv} [Value: {write_value}]"
                )

    def poll(self):
        poll()


if __name__ == "__main__":
    device = EpicsDevice(attribute_pv_dict=ATTRIBUTE_PV_DICT)
    device.list_pvs()
    device.step = 2
    while True:
        time.sleep(1)
        print(device.ramper)
