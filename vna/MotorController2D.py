"""
二维电机运动控制器
基于EPICS架构实现双方向（X轴和Y轴）电机运动控制

该模块提供：
- X轴和Y轴独立的位置、速度控制
- 双轴联动控制功能
- 限位保护和紧急停止功能
- EPICS PV接口，支持远程控制
"""

import time
import threading
from typing import Tuple, Optional, Dict, Any
from enum import Enum

import epics
from epics import PV


class MotorState(Enum):
    """电机状态枚举"""
    STOPPED = 0      # 停止
    MOVING = 1       # 运动中
    ERROR = 2        # 错误
    READY = 3        # 就绪
    LIMIT = 4        # 触发限位


class AxisConfig:
    """轴配置类"""
    def __init__(self, 
                 prefix: str, 
                 axis_name: str, 
                 velocity_max: float = 10.0,
                 acceleration: float = 5.0,
                 position_limits: Tuple[float, float] = (-1000.0, 1000.0)):
        """
        初始化轴配置
        
        Args:
            prefix: EPICS PV前缀
            axis_name: 轴名称 ('x' 或 'y')
            velocity_max: 最大速度
            acceleration: 加速度
            position_limits: 位置限制 (min, max)
        """
        self.prefix = prefix
        self.axis_name = axis_name
        self.velocity_max = velocity_max
        self.acceleration = acceleration
        self.position_limits = position_limits


class TwoDimensionalMotorController:
    """
    二维电机运动控制器
    
    控制X轴和Y轴两个方向的电机，提供位置、速度控制等功能
    """
    
    def __init__(self, 
                 device_prefix: str, 
                 x_axis_config: AxisConfig, 
                 y_axis_config: AxisConfig):
        """
        初始化二维电机控制器
        
        Args:
            device_prefix: 设备PV前缀
            x_axis_config: X轴配置
            y_axis_config: Y轴配置
        """
        self.device_prefix = device_prefix
        self.x_axis_config = x_axis_config
        self.y_axis_config = y_axis_config
        
        # 当前状态
        self._x_position = 0.0
        self._y_position = 0.0
        self._x_velocity = 0.0
        self._y_velocity = 0.0
        self._x_target = 0.0
        self._y_target = 0.0
        
        # 状态变量
        self._x_state = MotorState.STOPPED
        self._y_state = MotorState.STOPPED
        self._emergency_stop = False
        
        # PV对象字典
        self._pvs = {}  # type: Dict[str, PV]
        
        # 启动EPICS PV连接
        self._connect_pvs()
        
        # 启动监控线程
        self._monitoring_thread = threading.Thread(target=self._monitor_positions, daemon=True)
        self._monitoring_thread.start()
        
        print(f"二维电机控制器已初始化，设备前缀: {device_prefix}")
    
    def _connect_pvs(self):
        """连接到EPICS PVs"""
        # X轴PVs
        x_pv_names = [
            f"{self.device_prefix}{self.x_axis_config.axis_name}:position",      # 实际位置
            f"{self.device_prefix}{self.x_axis_config.axis_name}:target",        # 目标位置
            f"{self.device_prefix}{self.x_axis_config.axis_name}:velocity",      # 速度
            f"{self.device_prefix}{self.x_axis_config.axis_name}:move",          # 移动指令
            f"{self.device_prefix}{self.x_axis_config.axis_name}:stop",          # 停止指令
            f"{self.device_prefix}{self.x_axis_config.axis_name}:state",         # 状态
            f"{self.device_prefix}{self.x_axis_config.axis_name}:limit-low",     # 低限位
            f"{self.device_prefix}{self.x_axis_config.axis_name}:limit-high",    # 高限位
        ]
        
        # Y轴PVs
        y_pv_names = [
            f"{self.device_prefix}{self.y_axis_config.axis_name}:position",      # 实际位置
            f"{self.device_prefix}{self.y_axis_config.axis_name}:target",        # 目标位置
            f"{self.device_prefix}{self.y_axis_config.axis_name}:velocity",      # 速度
            f"{self.device_prefix}{self.y_axis_config.axis_name}:move",          # 移动指令
            f"{self.device_prefix}{self.y_axis_config.axis_name}:stop",          # 停止指令
            f"{self.device_prefix}{self.y_axis_config.axis_name}:state",         # 状态
            f"{self.device_prefix}{self.y_axis_config.axis_name}:limit-low",     # 低限位
            f"{self.device_prefix}{self.y_axis_config.axis_name}:limit-high",    # 高限位
        ]
        
        # 总体控制PVs
        general_pv_names = [
            f"{self.device_prefix}emergency-stop",                               # 紧急停止
            f"{self.device_prefix}position:x",                                  # 当前X位置
            f"{self.device_prefix}position:y",                                  # 当前Y位置
            f"{self.device_prefix}target:x",                                    # 目标X位置
            f"{self.device_prefix}target:y",                                    # 目标Y位置
            f"{self.device_prefix}status",                                      # 状态
            f"{self.device_prefix}move-xy",                                     # XY联动移动
        ]
        
        # 创建PV对象
        all_pv_names = x_pv_names + y_pv_names + general_pv_names
        for pv_name in all_pv_names:
            pv = PV(pv_name)
            self._pvs[pv_name] = pv
            
        # 等待所有PV连接
        for pv_name, pv_obj in self._pvs.items():
            if not pv_obj.wait_for_connection(timeout=5.0):
                print(f"警告: PV {pv_name} 连接超时")
    
    def _monitor_positions(self):
        """后台监控位置变化的线程"""
        while True:
            try:
                # 更新X轴位置
                x_pos_pv = self._pvs[f"{self.device_prefix}{self.x_axis_config.axis_name}:position"]
                if x_pos_pv.connected:
                    self._x_position = x_pos_pv.get() or 0.0
                
                # 更新Y轴位置
                y_pos_pv = self._pvs[f"{self.device_prefix}{self.y_axis_config.axis_name}:position"]
                if y_pos_pv.connected:
                    self._y_position = y_pos_pv.get() or 0.0
                
                # 更新到总线PV
                pos_x_pv = self._pvs[f"{self.device_prefix}position:x"]
                pos_y_pv = self._pvs[f"{self.device_prefix}position:y"]
                
                if pos_x_pv.connected:
                    pos_x_pv.put(self._x_position)
                if pos_y_pv.connected:
                    pos_y_pv.put(self._y_position)
                
                # 检查限位状态
                self._check_limits()
                
                time.sleep(0.1)  # 每100ms更新一次
            except Exception as e:
                print(f"监控位置时出错: {e}")
                time.sleep(1.0)
    
    def _check_limits(self):
        """检查限位开关状态"""
        # 检查X轴限位
        x_low_pv = self._pvs[f"{self.device_prefix}{self.x_axis_config.axis_name}:limit-low"]
        x_high_pv = self._pvs[f"{self.device_prefix}{self.x_axis_config.axis_name}:limit-high"]
        
        if x_low_pv.connected and x_low_pv.get() or x_high_pv.connected and x_high_pv.get():
            self._x_state = MotorState.LIMIT
            self.stop_x()
        
        # 检查Y轴限位
        y_low_pv = self._pvs[f"{self.device_prefix}{self.y_axis_config.axis_name}:limit-low"]
        y_high_pv = self._pvs[f"{self.device_prefix}{self.y_axis_config.axis_name}:limit-high"]
        
        if y_low_pv.connected and y_low_pv.get() or y_high_pv.connected and y_high_pv.get():
            self._y_state = MotorState.LIMIT
            self.stop_y()
    
    def move_absolute_x(self, position: float, velocity: Optional[float] = None):
        """
        X轴绝对位置移动
        
        Args:
            position: 目标位置
            velocity: 移动速度（可选）
        """
        if self._emergency_stop:
            print("紧急停止状态下无法移动")
            return False
            
        # 检查位置限制
        min_pos, max_pos = self.x_axis_config.position_limits
        if not (min_pos <= position <= max_pos):
            print(f"X轴目标位置超出范围: [{min_pos}, {max_pos}]")
            return False
        
        # 设置目标位置
        target_pv = self._pvs[f"{self.device_prefix}{self.x_axis_config.axis_name}:target"]
        if target_pv.connected:
            target_pv.put(position)
            self._x_target = position
        
        # 设置速度（如果提供）
        if velocity is not None:
            vel_pv = self._pvs[f"{self.device_prefix}{self.x_axis_config.axis_name}:velocity"]
            if vel_pv.connected:
                max_vel = self.x_axis_config.velocity_max
                actual_vel = min(abs(velocity), max_vel)
                vel_pv.put(actual_vel)
        
        # 发送移动指令
        move_pv = self._pvs[f"{self.device_prefix}{self.x_axis_config.axis_name}:move"]
        if move_pv.connected:
            move_pv.put(1)
            self._x_state = MotorState.MOVING
        
        return True
    
    def move_absolute_y(self, position: float, velocity: Optional[float] = None):
        """
        Y轴绝对位置移动
        
        Args:
            position: 目标位置
            velocity: 移动速度（可选）
        """
        if self._emergency_stop:
            print("紧急停止状态下无法移动")
            return False
            
        # 检查位置限制
        min_pos, max_pos = self.y_axis_config.position_limits
        if not (min_pos <= position <= max_pos):
            print(f"Y轴目标位置超出范围: [{min_pos}, {max_pos}]")
            return False
        
        # 设置目标位置
        target_pv = self._pvs[f"{self.device_prefix}{self.y_axis_config.axis_name}:target"]
        if target_pv.connected:
            target_pv.put(position)
            self._y_target = position
        
        # 设置速度（如果提供）
        if velocity is not None:
            vel_pv = self._pvs[f"{self.device_prefix}{self.y_axis_config.axis_name}:velocity"]
            if vel_pv.connected:
                max_vel = self.y_axis_config.velocity_max
                actual_vel = min(abs(velocity), max_vel)
                vel_pv.put(actual_vel)
        
        # 发送移动指令
        move_pv = self._pvs[f"{self.device_prefix}{self.y_axis_config.axis_name}:move"]
        if move_pv.connected:
            move_pv.put(1)
            self._y_state = MotorState.MOVING
        
        return True
    
    def move_absolute_xy(self, x: float, y: float, velocity: Optional[float] = None):
        """
        XY轴同时绝对位置移动
        
        Args:
            x: X轴目标位置
            y: Y轴目标位置
            velocity: 移动速度（可选）
        """
        # 同时设置X和Y轴
        success_x = self.move_absolute_x(x, velocity)
        success_y = self.move_absolute_y(y, velocity)
        
        # 更新XY联动PV
        move_xy_pv = self._pvs[f"{self.device_prefix}move-xy"]
        if move_xy_pv.connected:
            move_xy_pv.put(1)
        
        return success_x and success_y
    
    def move_relative_x(self, offset: float, velocity: Optional[float] = None):
        """
        X轴相对位置移动
        
        Args:
            offset: 位置偏移量
            velocity: 移动速度（可选）
        """
        new_pos = self._x_position + offset
        return self.move_absolute_x(new_pos, velocity)
    
    def move_relative_y(self, offset: float, velocity: Optional[float] = None):
        """
        Y轴相对位置移动
        
        Args:
            offset: 位置偏移量
            velocity: 移动速度（可选）
        """
        new_pos = self._y_position + offset
        return self.move_absolute_y(new_pos, velocity)
    
    def move_relative_xy(self, x_offset: float, y_offset: float, velocity: Optional[float] = None):
        """
        XY轴同时相对位置移动
        
        Args:
            x_offset: X轴位置偏移量
            y_offset: Y轴位置偏移量
            velocity: 移动速度（可选）
        """
        new_x = self._x_position + x_offset
        new_y = self._y_position + y_offset
        return self.move_absolute_xy(new_x, new_y, velocity)
    
    def stop_x(self):
        """停止X轴运动"""
        stop_pv = self._pvs[f"{self.device_prefix}{self.x_axis_config.axis_name}:stop"]
        if stop_pv.connected:
            stop_pv.put(1)
        self._x_state = MotorState.STOPPED
    
    def stop_y(self):
        """停止Y轴运动"""
        stop_pv = self._pvs[f"{self.device_prefix}{self.y_axis_config.axis_name}:stop"]
        if stop_pv.connected:
            stop_pv.put(1)
        self._y_state = MotorState.STOPPED
    
    def stop_xy(self):
        """停止XY轴运动"""
        self.stop_x()
        self.stop_y()
    
    def emergency_stop(self):
        """紧急停止"""
        self.stop_xy()
        self._emergency_stop = True
        
        # 更新紧急停止PV
        estop_pv = self._pvs[f"{self.device_prefix}emergency-stop"]
        if estop_pv.connected:
            estop_pv.put(1)
    
    def release_emergency_stop(self):
        """释放紧急停止"""
        self._emergency_stop = False
        
        # 更新紧急停止PV
        estop_pv = self._pvs[f"{self.device_prefix}emergency-stop"]
        if estop_pv.connected:
            estop_pv.put(0)
    
    def get_current_position(self) -> Tuple[float, float]:
        """获取当前位置"""
        return (self._x_position, self._y_position)
    
    def get_target_position(self) -> Tuple[float, float]:
        """获取目标位置"""
        return (self._x_target, self._y_target)
    
    def is_x_moving(self) -> bool:
        """X轴是否在移动"""
        return self._x_state == MotorState.MOVING
    
    def is_y_moving(self) -> bool:
        """Y轴是否在移动"""
        return self._y_state == MotorState.MOVING
    
    def is_moving(self) -> bool:
        """是否任意轴在移动"""
        return self.is_x_moving() or self.is_y_moving()


# 示例用法
if __name__ == "__main__":
    # 创建X轴配置
    x_config = AxisConfig(
        prefix="motor:",
        axis_name="x",
        velocity_max=50.0,
        acceleration=20.0,
        position_limits=(-100.0, 100.0)
    )
    
    # 创建Y轴配置
    y_config = AxisConfig(
        prefix="motor:",
        axis_name="y",
        velocity_max=30.0,
        acceleration=15.0,
        position_limits=(-50.0, 50.0)
    )
    
    # 创建二维电机控制器
    controller = TwoDimensionalMotorController(
        device_prefix="2d-motor:",
        x_axis_config=x_config,
        y_axis_config=y_config
    )
    
    # 示例移动
    print("移动到 (10, 5)")
    controller.move_absolute_xy(10.0, 5.0)
    
    time.sleep(2)
    
    print("当前位置:", controller.get_current_position())
    
    print("相对移动 (+5, +3)")
    controller.move_relative_xy(5.0, 3.0)
    
    time.sleep(2)
    
    print("当前位置:", controller.get_current_position())