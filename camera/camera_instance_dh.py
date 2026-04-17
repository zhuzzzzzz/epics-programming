import os

os.environ["EPICS_CA_MAX_ARRAY_BYTES"] = "5000000"

import logging
import argparse
from pcaspy import SimpleServer
from ioc_driver import IOCDriver
from CameraDeviceDH import CameraDeviceDH


logger = logging.getLogger(__name__)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="启动大恒相机IOC")
    parser.add_argument(
        "--exception-verbose", action="store_true", help="启用异常日志详细输出"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="设置日志级别 (默认: INFO)",
    )
    parser.add_argument(
        "--device-name", type=str, default="", help='设备名称 (默认: "")'
    )
    parser.add_argument(
        "--device-addr",
        type=str,
        default="192.168.1.200",
        help="设备地址 (默认: 192.168.1.200)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    numeric_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"无效的日志级别: {args.log_level}")

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("pcaspy").setLevel(logging.INFO)

    server = SimpleServer()
    dev_camera = CameraDeviceDH(
        device_name=args.device_name,
        device_addr=args.device_addr,
        verbose=args.exception_verbose,
    )
    dev_camera.list_pvs()
    server.createPV(dev_camera.PV_Prefix, dev_camera.PV_DB)
    driver = IOCDriver(device=dev_camera)
    while True:
        server.process(0.1)
