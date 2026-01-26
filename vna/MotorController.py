from epics import PV
from typing import Tuple


PV_SUFFIX = {
    "enabled": ":motor_en",
    "state_code": "motor_error_code",
    "position": "real_pos_value",
    "relative_velocity": "motor_auto_move_relative_velocity",
    "relative_instance": "motor_auto_move_relative_distance",
    "lower_limit": "negative_limit_X",
    "upper_limit": "positive_limit_X",
}


def gen_pv(prefix: str, suffix: str, return_name: bool = False):
    pv_name = f"{prefix}:{suffix}" if prefix else suffix
    if return_name:
        return pv_name
    return PV(pv_name)


class AxisController:
    """轴控制"""

    def __init__(
        self,
        device_name: str,
        axis_name: str,
        velocity_max: float = 10.0,
        position_limits: Tuple[float, float] = (-100.0, 100.0),
        pv_suffix: dict = PV_SUFFIX,
    ):
        """
        初始化轴配置

        Args:
            device_name: 设备名称(用于EPICS PV前缀)
            axis_name: 轴名称('x'或'y')
            velocity_max: 最大速度
            position_limits: 位置限制(min,max)
            pv_suffix: 存储PV名称后缀的字典,以功能名称为键,传入新字典以覆盖默认值
        """
        self.device_name = device_name
        self.axis_name = axis_name
        self.velocity_max = velocity_max
        self.position_limits = position_limits
        self.timeout = 3.0
        self.pvs = {
            key: gen_pv(device_name, suffix) for key, suffix in pv_suffix.items()
        }

    def __repr__(self):
        return f'AxisController("{self.device_name}", "{self.axis_name}")'

    @property
    def enabled(self):
        return self.pvs["enabled"].get()

    @property
    def state_code(self):
        return self.pvs["state_code"].get()

    @property
    def position(self):
        return self.pvs["enabled"].get()

    @property
    def relative_velocity(self):
        return self.pvs["releative_instance"].get()

    @relative_velocity.setter
    def relative_velocity(self, value: float):
        self.pvs["relative_velocity"].put(value, wait=True, timeout=self.timeout)

    @property
    def relative_instance(self):
        return self.pvs["releative_instance"].get()

    @relative_instance.setter
    def relative_instance(self, value: float):
        self.pvs["relative_instance"].put(value, wait=True, timeout=self.timeout)

    @property
    def lower_limit(self):
        value = self.pvs["lower_limit"].get()
        if value is not None:
            return value
        else:
            raise ValueError(f"{str(self)}: Lower limit reached.")

    @property
    def upper_limit(self):
        value = self.pvs["upper_limit"].get()
        if value is not None:
            return value
        else:
            raise ValueError(f"{str(self)}: Upper limit reached.")

    def move_f(self):
        # check limit
        # pv.put
        # wait for done
        # return
        pass

    def move_b(self):
        # check limit
        # pv.put
        # wait for done
        # return
        pass

    def stop(self):
        pass

    def reset(self):
        pass

    def wait_for_pvs_connection(self):
        """连接EPICS PVs"""
        for pv in self.pvs.values():
            if not pv.wait_for_connection(timeout=self.timeout):
                raise TimeoutError(
                    f'{str(self)}: Connection timeout for PV "{pv.pvname}".'
                )


class MotorController2D:
    def __init__(self, name, address, x_axis_controller, y_axis_controller):
        self.name = name
        self.address = address
        self.x_AxisCtrl = x_axis_controller
        self.y_AxisCtrl = y_axis_controller


if __name__ == "__main__":
    test_motor_axis_x = AxisController("Test:MotorX", "X")
    test_motor_axis_z = AxisController("Test:MotorZ", "z")
    test_motor = MotorController2D(
        "TEST", "taddress", test_motor_axis_x, test_motor_axis_z
    )
