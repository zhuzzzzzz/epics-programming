import os

os.environ["EPICS_CA_MAX_ARRAY_BYTES"] = "5000000"

import logging
import argparse
from pcaspy import SimpleServer
from ioc_driver import IOCDriver
from CameraDeviceDH import CameraDeviceDH, camera_device_dh

logger = logging.getLogger(__name__)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="启动大恒相机IOC")
    parser.add_argument(
        "--device-name", type=str, default="", help='设备名称 (默认: "")'
    )
    parser.add_argument(
        "--device-addr",
        type=str,
        default="192.168.1.200",
        help="设备地址 (默认: 192.168.1.200)",
    )
    parser.add_argument(
        "--pv-update-interval",
        type=float,
        default=3.0,
        help="设备属性PV更新时间间隔 (默认: 3.0s)",
    )
    parser.add_argument(
        "--device-detect-interval",
        type=float,
        default=3.0,
        help="设备状态检测时间间隔 (默认: 3.0s)",
    )
    parser.add_argument(
        "--device-reconnect-interval",
        type=float,
        default=30.0,
        help="设备重连时间间隔 (默认: 30.0s)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="设置日志级别 (默认: INFO)",
    )
    parser.add_argument(
        "--driver-log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="设置ioc_driver日志级别 (默认: INFO)",
    )
    parser.add_argument(
        "--exception-verbose", action="store_true", help="启用相机异常日志详细输出"
    )
    parser.add_argument(
        "--performance-stat", action="store_true", help="启用相机性能统计"
    )
    parser.add_argument(
        "--result-stat", action="store_true", help="启用相机拟合结果统计"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    numeric_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"无效的日志级别: {args.log_level}")
    numeric_level_for_driver = getattr(logging, args.driver_log_level.upper(), None)
    if not isinstance(numeric_level_for_driver, int):
        raise ValueError(f"无效的ioc_driver日志级别: {args.driver_log_level}")

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("pcaspy").setLevel(logging.INFO)
    logging.getLogger("ioc_driver").setLevel(numeric_level_for_driver)

    if args.performance_stat:
        camera_device_dh.performance_stat = True
    if args.result_stat:
        camera_device_dh.result_stat = True

    pv_update_interval = args.pv_update_interval
    device_detect_interval = args.device_detect_interval
    device_reconnect_interval = args.device_reconnect_interval

    server = SimpleServer()
    dev_camera = CameraDeviceDH(
        device_name=args.device_name,
        device_addr=args.device_addr,
        verbose=args.exception_verbose,
    )
    dev_camera.list_pvs()
    server.createPV(dev_camera.PV_Prefix, dev_camera.PV_DB)
    driver = IOCDriver(
        device=dev_camera,
        update_interval=pv_update_interval,
        detect_interval=device_detect_interval,
        reconnect_interval=device_reconnect_interval,
    )
    dev_camera.connect()
    while True:
        server.process(0.1)
