import time
from datetime import datetime, timezone
import argparse
import pyvisa
from epics import PV, poll

# Mapping attribute name to PV name
# "attribute_name": ("PV_name_get", ["PV_name_put"])
ATTRIBUTE_PV_DICT_X = {
    "enabled": ("Test:MotorX:motor_en_done", "Test:MotorX:motor_en"),
    "state_code": ("Test:MotorX:motor_error_code",),
    "position": (
        "Test:MotorX:real_pos_value",
        "Test:MotorX:motor_auto_move_absolute_position",
    ),
    "velocity": (
        "Test:Motor:XRealAbsSpeedBak",
        "Test:MotorX:motor_auto_move_absolute_velocity",
    ),
    "move": ("Test:MotorX:motor_auto_move_absolute_r",),
    "done": ("Test:MotorX:motor_auto_move_absolute_active",),
    "stop": ("Test:MotorX:motor_stop_r",),
    "lower_limit": ("Test:Motor:negative_limit_X",),
    "upper_limit": ("Test:Motor:positive_limit_X",),
    "reset": ("Test:BPM:Reset_Test_X",),
}
ATTRIBUTE_PV_DICT_Z = {
    "enabled": ("Test:MotorZ:motor_en_done", "Test:MotorZ:motor_en"),
    "state_code": ("Test:MotorZ:motor_error_code",),
    "position": (
        "Test:MotorZ:real_pos_value",
        "Test:MotorZ:motor_auto_move_absolute_position",
    ),
    "velocity": (
        "Test:Motor:YRealAbsSpeedBak",
        "Test:MotorZ:motor_auto_move_absolute_velocity",
    ),
    "move": ("Test:MotorZ:motor_auto_move_absolute_r",),
    "done": ("Test:MotorZ:motor_auto_move_absolute_active",),
    "stop": ("Test:MotorZ:motor_stop_r",),
    "lower_limit": ("Test:Motor:negative_limit_Z",),
    "upper_limit": ("Test:Motor:positive_limit_Z",),
    "reset": ("Test:BPM:Reset_Test_Z",),
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
            self._wait_for_pvs_connection()

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

    def _wait_for_pvs_connection(self):
        for pv_tuple in self._pvs.values():
            for pv in pv_tuple:
                if not pv.wait_for_connection(timeout=self._timeout):
                    raise TimeoutError(
                        f'{str(self)}: Connection timeout for PV "{pv.pvname}".'
                    )

    def _list_pvs(self):
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

    def _poll(self):
        poll()


class AxisController(EpicsDevice):
    def __init__(
        self,
        device_name: str,
        axis_name: str,
        attribute_pv_dict: dict = ATTRIBUTE_PV_DICT_X,
        pv_timeout: float = 3.0,
        motor_timeout: float = 5.0,
        motor_wait: float = 0.0,
    ):
        """
        电机轴控制器, 继承EpicsDevice类

        Args:
            device_name: 设备名称
            axis_name: 轴名称(如'x', 'y', 'z'等)
            attribute_pv_dict: 属性到PV名称的映射字典, 定义了控制轴所需的PV
            pv_timeout: EPICS PV连接超时时间(秒)
            motor_timeout: 单次电机移动操作的最大超时时间(秒)
            motor_wait: 电机移动后等待的时间(秒)
        """
        super().__init__(
            name=f"{device_name}-{axis_name}",
            attribute_pv_dict=attribute_pv_dict,
            timeout=pv_timeout,
        )

        self._device_name = device_name
        self._axis_name = axis_name
        self._motor_timeout = motor_timeout
        self._motor_wait = motor_wait

    def _move(self):
        start_time = time.time()
        self.move = 1
        while True:
            self._wait_and_check()
            if not self.done:
                time.sleep(self._motor_wait)
                break
            elapsed_time = time.time() - start_time
            if elapsed_time > self._motor_timeout:
                raise TimeoutError(f"Motor timeout.")

    def _stop(self):
        self.stop = 1

    def _reset(self):
        start_time = time.time()
        self.reset = 1
        while True:
            self._wait_and_check()
            if not self.done:
                time.sleep(self._motor_wait)
                break
            elapsed_time = time.time() - start_time
            if elapsed_time > self._motor_timeout:
                raise TimeoutError(f"Motor timeout.")

    def _wait_and_check(self):
        # value check
        self._poll()
        if self.state_code:
            raise RuntimeError(f"{str(self)}: Motor error with code {self.state_code}.")
        if not self.lower_limit:
            raise RuntimeError(f"{str(self)}: Motor reached lower limit.")
        if not self.upper_limit:
            raise RuntimeError(f"{str(self)}: Motor reached upper limit.")


class VnaDevice:
    def __init__(
        self,
        name: str = "P9382B",
        address: str = "TCPIP0::localhost::hislip_PXI0_CHASSIS1_SLOT1_INDEX0::INSTR",
        timeout: float = 10.0,
    ):
        """
        Args:
            name: 设备名称
            address: 设备地址
            timeout: 通信超时时间(秒)
        """
        self.name = name
        self.address = address
        self.timeout = timeout
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(address)
        self.inst.timeout = 1000 * timeout

    def __str__(self):
        return f"{self.name}@{self.address}"

    @property
    def is_connect(self):
        return any(self.inst.query("*IDN?"))

    def measure_trace(self, trace_id=1):
        results = self.inst.query_ascii_values(f"CALC:MEAS{trace_id}:DATA:FDATA?")
        xValues = self.inst.query_ascii_values(f"CALC:MEAS{trace_id}:X:VAL?")
        return xValues, results

    def measure_marker(self, trace_id=1):
        makerX1 = self.inst.query_ascii_values(f"CALC:MEAS{trace_id}:MARK1:X?")
        makerY1 = self.inst.query_ascii_values(f"CALC:MEAS{trace_id}:MARK1:Y?")
        return makerX1, makerY1


def parse_arguments():
    """解析命令行参数，返回参数命名空间"""
    parser = argparse.ArgumentParser(description="自动化电机扫描测量程序")
    parser.add_argument("task_name", help="任务名称")
    parser.add_argument(
        "sweep_axis",
        choices=["x", "X", "z", "Z"],
        help="扫描轴. 默认: x轴",
    )
    parser.add_argument(
        "sweep_start",
        nargs="?",
        type=float,
        default=-3.0,
        help="扫描起始位置. 默认: -3.0 (mm)",
    )
    parser.add_argument(
        "sweep_end",
        nargs="?",
        type=float,
        default=3.0,
        help="扫描结束位置. 默认: 3.0 (mm)",
    )
    parser.add_argument(
        "sweep_step",
        nargs="?",
        type=float,
        default=0.1,
        help="扫描步长. 默认: 0.1 (mm)",
    )
    parser.add_argument(
        "motor_velocity",
        nargs="?",
        type=float,
        default=0.5,
        help="电机速度. 默认: 0.5 (mm/s)",
    )
    parser.add_argument(
        "measure_repeat",
        nargs="?",
        type=int,
        default=5,
        help="重复读取VNA测量曲线次数. 默认: 5 (次)",
    )

    return parser.parse_args()


if __name__ == "__main__":
    # 解析命令行参数
    args = parse_arguments()
    task_name = args.task_name
    sweep_axis = args.sweep_axis
    sweep_settings = (args.sweep_start, args.sweep_end, args.sweep_step)
    motor_velocity = args.motor_velocity
    measure_repeat = args.measure_repeat
    # 其他默认参数
    motor_velocity_max = 2
    pv_timeout = 3.0
    motor_timeout = 10.0
    motor_wait = 3.0
    motor_check_wait = 30.0
    vna_timeout = 10.0
    measure_wait = 1.0
    # 参数校验
    if (
        sweep_settings[0] <= -10
        or sweep_settings[1] >= 10
        or sweep_settings[1] <= sweep_settings[0]
    ):
        print("error: Invalid sweep settings.")
        exit(1)
    if motor_velocity <= 0 or motor_velocity > motor_velocity_max:
        print("error: Invalid motor velocity.")
        exit(1)
    print(
        f"VnaScanProcess ------ "
        f"任务名称:{task_name} "
        f"扫描轴:{sweep_axis} "
        f"扫描设置:{sweep_settings} "
        f"速度:{motor_velocity} "
        f"VNA数据重复测量次数:{measure_repeat} "
    )
    # 连接 VNA
    vna = VnaDevice(timeout=vna_timeout)
    if not vna.is_connect:
        print("error: VNA not connected.")
        exit(1)
    # 连接电机
    if sweep_axis.lower() == "x":
        axis = AxisController(
            device_name="Motor",
            axis_name="X",
            attribute_pv_dict=ATTRIBUTE_PV_DICT_X,
            pv_timeout=pv_timeout,
            motor_timeout=motor_timeout,
            motor_wait=motor_wait,
        )
    elif sweep_axis.lower() == "z":
        axis = AxisController(
            device_name="Motor",
            axis_name="Z",
            attribute_pv_dict=ATTRIBUTE_PV_DICT_Z,
            pv_timeout=pv_timeout,
            motor_timeout=motor_timeout,
            motor_wait=motor_wait,
        )
    else:
        print("error: Invalid sweep axis.")
        exit(1)
    try:
        axis._wait_for_pvs_connection()
    except TimeoutError as e:
        print(f"error: Setup PV connection timeout. {str(e)}")
        exit(1)
    # 电机初始化设置
    axis.velocity = motor_velocity
    # 开始扫描
    print(f"开始扫描... ")
    sweep_result1 = []
    sweep_result2 = []
    pos = sweep_settings[0]
    step = sweep_settings[2]
    while pos <= sweep_settings[1]:
        pos = round(pos, 2)
        print(f"测量位置 {pos} ...")
        axis.position = pos
        print(f"移动电机 ...")
        axis._move()
        print(f"电机到达指定位置.")
        #
        start_time = time.time()
        while True:
            axis._poll()
            if abs(axis.position - pos) < 1e-3:
                print(f"确认电机到达指定位置.")
                break
            elapsed_time = time.time() - start_time
            if elapsed_time > motor_check_wait:
                raise TimeoutError(f"Motor timeout. 确认电机到达指定位置超时.")
        #
        tr1_xValues = None
        tr1_xMarker = None
        tr2_xValues = None
        tr2_xMarker = None
        tr1_results = []
        tr1_marker_results = []
        tr2_results = []
        tr2_marker_results = []
        print(f"获取VNA测量数据 ...")
        for i in range(measure_repeat):
            time.sleep(measure_wait)
            tr1_xValues, tr1_temp_trace_results = vna.measure_trace(trace_id=1)
            tr1_xMarker, tr1_temp_marker_results = vna.measure_marker(trace_id=1)
            tr1_results.append(tr1_temp_trace_results)
            tr1_marker_results.append(tr1_temp_marker_results)
            tr2_xValues, tr2_temp_trace_results = vna.measure_trace(trace_id=2)
            tr2_xMarker, tr2_temp_marker_results = vna.measure_marker(trace_id=2)
            tr2_results.append(tr2_temp_trace_results)
            tr2_marker_results.append(tr2_temp_marker_results)
        print(f"处理测量数据 ...")
        tr1_avg_trace_results = [sum(x) / len(x) for x in zip(*tr1_results)]
        tr1_max_result = max(tr1_avg_trace_results)
        tr1_x_for_max_result = tr1_xValues[tr1_avg_trace_results.index(tr1_max_result)]
        tr1_avg_marker_results = [sum(x) / len(x) for x in zip(*tr1_marker_results)]
        sweep_result1.append(
            (
                pos,
                tr1_x_for_max_result,
                tr1_max_result,
                tr1_xMarker[0],
                tr1_avg_marker_results[0],
            )
        )
        tr2_avg_trace_results = [sum(x) / len(x) for x in zip(*tr2_results)]
        tr2_max_result = max(tr2_avg_trace_results)
        tr2_x_for_max_result = tr2_xValues[tr2_avg_trace_results.index(tr2_max_result)]
        tr2_avg_marker_results = [sum(x) / len(x) for x in zip(*tr2_marker_results)]
        sweep_result2.append(
            (
                pos,
                tr2_x_for_max_result,
                tr2_max_result,
                tr2_xMarker[0],
                tr2_avg_marker_results[0],
            )
        )
        pos += step
        if pos > sweep_settings[1]:
            print(f"电机复位 ...")
            axis._reset()
            break
    # 写入txt
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename1 = f"{task_name}-{sweep_axis}1-{ts}.txt"
    filename2 = f"{task_name}-{sweep_axis}2-{ts}.txt"
    with open(filename1, "w") as f:
        f.write("#Position Freq_at_Max_dB Max_dB MarkerX MarkerY\n")
        for item in sweep_result1:
            f.write(
                f"{item[0]:.2f} {item[1]/1e6:.3f} {item[2]*1e3:.3f} {item[3]/1e6:.3f} {item[4]*1e3:.3f}\n"
            )
        else:
            print(f"写入{filename1}. ")
    with open(filename2, "w") as f:
        f.write("#Position Freq_at_Max_dB Max_dB MarkerX MarkerY\n")
        for item in sweep_result2:
            f.write(
                f"{item[0]:.2f} {item[1]/1e6:.3f} {item[2]*1e3:.3f} {item[3]/1e6:.3f} {item[4]*1e3:.3f}\n"
            )
        else:
            print(f"写入{filename2}. ")
    print(f"扫描完成. ")
