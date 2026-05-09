import time
import logging
import queue
import threading
import gxipy as gx
import numpy as np
from scipy.optimize import curve_fit
from epics_device import EpicsDevice

logger = logging.getLogger(__name__)

IMAGE_HEIGHT = 1024
IMAGE_WIDTH = 1280
ROI_HEIGHT = 500
ROI_WIDTH = 500

TEST_DURATION = 10

ITERATION_LIMIT = 1000

THREAD_NUM = 1
QUEUE_SIZE = 3


class CameraDeviceDH(EpicsDevice):

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
        "Width": {
            "type": "int",
            "asyn": True,
        },
        "Height": {
            "type": "int",
            "asyn": True,
        },
        "IMAGE": {
            "type": "char",
            "asyn": True,
            "count": IMAGE_HEIGHT * IMAGE_WIDTH,
        },
        "ROI_IMAGE": {
            "type": "char",
            "asyn": True,
            "count": ROI_HEIGHT * ROI_WIDTH,
        },
        "PIXEL_LENGTH": {
            "type": "float",
            "asyn": True,
            "value": 0.01,
        },
        "ROI_X_START": {
            "type": "int",
            "asyn": True,
        },
        "ROI_Y_START": {
            "type": "int",
            "asyn": True,
        },
        "ROI_X_DATA": {
            "type": "int",
            "asyn": True,
            "count": ROI_WIDTH,
        },
        "ROI_Y_DATA": {
            "type": "int",
            "asyn": True,
            "count": ROI_HEIGHT,
        },
        "ROI_X_FIT_DATA": {
            "type": "float",
            "asyn": True,
            "count": ROI_WIDTH,
        },
        "ROI_Y_FIT_DATA": {
            "type": "float",
            "asyn": True,
            "count": ROI_HEIGHT,
        },
        "ROI_X_FIT_MAX": {
            "type": "float",
            "asyn": True,
        },
        "ROI_X_FIT_POS": {
            "type": "int",
            "asyn": True,
        },
        "ROI_X_FIT_POS_LEN": {
            "type": "float",
            "asyn": True,
        },
        "ROI_X_FIT_SIGMA": {
            "type": "float",
            "asyn": True,
        },
        "ROI_Y_FIT_MAX": {
            "type": "float",
            "asyn": True,
        },
        "ROI_Y_FIT_POS": {
            "type": "int",
            "asyn": True,
        },
        "ROI_Y_FIT_POS_LEN": {
            "type": "float",
            "asyn": True,
        },
        "ROI_Y_FIT_SIGMA": {
            "type": "float",
            "asyn": True,
        },
        "TRIGGER": {
            "type": "string",
            "asyn": True,
        },
        "TRIGGER_S": {
            "type": "int",
            "asyn": True,
        },
        "FRAME_ID": {
            "type": "int",
            "asyn": True,
        },
        "CCD_STATUS": {
            "type": "enum",
            "enums": ["CLOSED", "RUNNING", "ERROR"],
            "asyn": True,
        },
        "CCD_CTRL": {
            "type": "enum",
            "enums": ["STOP", "START"],
            "asyn": True,
        },
        "CCD_IOC_RESTART": {
            "type": "string",
            "asyn": True,
        },
    }

    # 允许直接向设备读取的属性值
    ATTR_READ_ALLOW_LIST = [
        "DeviceTemperature",
        "ExposureTime",
        "Gain",
        "TriggerSource",
        "Width",
        "Height",
    ]
    # 允许直接向设备写入的属性值
    ATTR_WRITE_ALLOW_LIST = [
        "ExposureTime",
        "Gain",
        "TriggerSource",
    ]
    # 允许执行操作的属性值
    ATTR_EXEC_ALLOW_LIST = [
        "TRIGGER",
        "TRIGGER_S",
        "CCD_CTRL",
        "CCD_IOC_RESTART",
    ]
    # 保留的属性值(不对设备进行操作)
    ATTR_RESERVE_LIST = [
        "IMAGE",
        "ROI_IMAGE",
        "PIXEL_LENGTH",
        "ROI_X_START",
        "ROI_Y_START",
        "ROI_X_DATA",
        "ROI_Y_DATA",
        "ROI_X_FIT_DATA",
        "ROI_Y_FIT_DATA",
        "ROI_X_FIT_MAX",
        "ROI_X_FIT_POS",
        "ROI_X_FIT_POS_LEN",
        "ROI_X_FIT_SIGMA",
        "ROI_Y_FIT_MAX",
        "ROI_Y_FIT_POS",
        "ROI_Y_FIT_POS_LEN",
        "ROI_Y_FIT_SIGMA",
        "FRAME_ID",
        "CCD_STATUS",
    ]

    performance_stat = False
    result_stat = False

    def __init__(self, device_name, device_addr, verbose=False):
        if not device_addr:
            return
        super().__init__(device_name, device_addr)
        #
        self.verbose = verbose  # 控制是否输出关于异常的详细日志
        self.process_queue_thread = [
            threading.Thread(
                target=process_queue_loop,
                name="process_queue_thread",
                daemon=True,
            )
            for i in range(THREAD_NUM)
        ]
        for thread_item in self.process_queue_thread:
            thread_item.start()
        # self.connect()

    def connect(self):
        if not hasattr(self, "device_driver") or self.device_driver is None:
            logger.error(f"can not connect before the device driver is initialized")
            return
        with self.connect_lock:
            if self.is_running:
                return
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
            self.device_driver.set_pv_value("CCD_STATUS", 1)
            self.is_running = True

    def reconnect(self):
        self.connect()

    def is_connected(self):
        try:
            self.camera.DeviceTemperature.get()
        except Exception:
            return False
        else:
            return True

    def handle_disconnect(self):
        if not self.connect_lock.acquire(blocking=False):
            logger.warning("get connect lock failed, skip handle_disconnect")
            return
        try:
            self.is_running = False
            self.device_driver.set_pv_value("CCD_STATUS", 2)
        finally:
            self.connect_lock.release()

    def close(self):
        with self.connect_lock:
            if not self.is_running:
                return
            self.is_running = False
            logger.info("send close signal")
            time.sleep(3)
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
                self.device_driver.set_pv_value("CCD_STATUS", 0)

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
            if attr == "TRIGGER":
                self.trigger()
            elif attr == "TRIGGER_S":
                self.trigger_test(frame_rate=value)
            elif attr == "CCD_CTRL":
                if value == 0:
                    self.close()
                elif value == 1:
                    self.connect()
            return None
        elif attr in self.ATTR_RESERVE_LIST:
            if attr == "ROI_X_START":
                if value < 0 or value >= IMAGE_WIDTH - ROI_WIDTH:
                    logger.warning(f'set_attr failed: "{attr}" out of range')
                    return False
                else:
                    # return None to let callback function handle it
                    return None
            if attr == "ROI_Y_START":
                if value < 0 or value >= IMAGE_HEIGHT - ROI_HEIGHT:
                    logger.warning(f'set_attr failed: "{attr}" out of range')
                    return False
                else:
                    # return None to let callback function handle it
                    return None
            if attr == "PIXEL_LENGTH":
                return None
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
        logger.debug("send software trigger command")
        try:
            self.camera.TriggerSoftware.send_command()
        except Exception as e:
            if self.verbose:
                logger.exception("trigger failed")
            else:
                logger.error(f"trigger failed: {e}")

    def trigger_test(self, frame_rate, test_duration=TEST_DURATION):
        logger.info(
            f"start frame rate test: trigger for {test_duration}s at frequency {frame_rate}Hz"
        )

        if self.performance_stat:
            fit_stat(reset=True)
            update_stat(reset=True)
            handle_stat(reset=True)
        if self.result_stat:
            result_stat(reset=True)

        period = 1.0 / frame_rate
        trigger_num = frame_rate * test_duration
        start_frame = self.device_driver.getParam("FRAME_ID")
        start_time = time.perf_counter()

        for i in range(1, trigger_num + 1):

            target_time = start_time + i * period

            while True:
                now = time.perf_counter()
                remain = target_time - now
                if remain <= 0:
                    break
                if remain > 0.002:
                    time.sleep(remain / 2)
            self.trigger()
            logger.debug(f"frame test: trigger number {i}")

        end_time = time.perf_counter()
        end_frame = self.device_driver.getParam("FRAME_ID")
        logger.info("end frame rate test")
        logger.info(
            f"frame test finished: effective trigger count {end_frame - start_frame}, rate {(end_frame - start_frame) / (end_time - start_time):.2f}fps"
        )
        if self.performance_stat:
            fit_stat(print_result=True)
            update_stat(print_result=True)
            handle_stat(print_result=True)
            logger.info(
                f"frame test finished: actual processing rate {handle_stat() / TEST_DURATION:.2f}fps"
            )
        if self.result_stat:
            result_stat(print_result=True)
            logger.info(
                f"frame test finished: actual processing rate {result_stat() / TEST_DURATION:.2f}fps"
            )


# 高斯函数
def gaussian(x, a, b, c):
    c = max(abs(c), 1e-6)
    return a * np.exp(-((x - b) ** 2) / (2 * c**2))


def create_time_stat(name):

    total_time = 0.0
    count = 0
    min_time = float("inf")
    max_time = 0.0

    def stat_func(elapsed=None, print_result=False, reset=False):
        nonlocal total_time, count, min_time, max_time

        if reset:
            total_time = 0.0
            count = 0
            min_time = float("inf")
            max_time = 0.0

        # 添加一次统计
        if elapsed is not None:
            total_time += elapsed
            count += 1

            min_time = min(min_time, elapsed)
            max_time = max(max_time, elapsed)

        # 输出统计结果
        if print_result:
            if count == 0:
                print(f"[{name}] 没有统计数据")
                return count

            avg_time = total_time / count

            print(f"[{name}] 运行时间统计")
            print(f"调用次数 : {count}")
            print(f"平均耗时 : {avg_time * 1000:.3f} ms")
            print(f"最小耗时 : {min_time * 1000:.3f} ms")
            print(f"最大耗时 : {max_time * 1000:.3f} ms")

        return count

    return stat_func


def create_string_stat(name):

    string_counts = {}
    total_count = 0

    def stat_func(string=None, print_result=False, reset=False):
        nonlocal string_counts, total_count

        if reset:
            string_counts.clear()
            total_count = 0

        # 添加统计
        if string is not None:
            string_counts[string] = string_counts.get(string, 0) + 1
            total_count += 1

        # 打印统计结果
        if print_result:
            if total_count == 0:
                print(f"[{name}] 没有字符串统计数据")
                return total_count

            print(f"[{name}] 字符串统计结果")
            print("-" * 50)
            print(f"{'字符串':<20} {'数量':<8} {'百分比':<10}")
            print("-" * 50)

            for string, count in sorted(
                string_counts.items(), key=lambda x: x[1], reverse=True
            ):
                percentage = (count / total_count) * 100
                print(f"{str(string):<20} {count:<8} {percentage:.2f}%")

            print("-" * 50)
            print(f"总计: {total_count} 条记录")

        return total_count

    return stat_func


camera_device_dh = CameraDeviceDH("", "")
handle_queue = queue.Queue(maxsize=QUEUE_SIZE)
handle_lock = threading.Lock()
fit_stat = create_time_stat("Gaussian Fit Time")
update_stat = create_time_stat("PV Update Time")
handle_stat = create_time_stat("Process Frame Time")
result_stat = create_string_stat("Result Stat")


def handle_image_CameraDeviceDH(raw_image):
    logger.debug(
        "callback get frame: ID=%d Height=%d Width=%d"
        % (raw_image.get_frame_id(), raw_image.get_height(), raw_image.get_width())
    )
    # create numpy array with data from raw image
    numpy_image = raw_image.get_numpy_array()
    numpy_image = numpy_image.copy()
    frame_id = raw_image.get_frame_id()
    try:
        handle_queue.put_nowait((numpy_image, frame_id))
    except queue.Full:
        logger.info("drop frame : ID=%d" % frame_id)


def process_queue_loop():
    while True:
        try:
            numpy_image, frame_id = handle_queue.get(timeout=1)
        except queue.Empty:
            continue
        process_frame(numpy_image, frame_id)


def process_frame(numpy_image, frame_id):
    logger.debug("start processing frame: ID=%d" % frame_id)
    if camera_device_dh.performance_stat:
        start_handle_time = time.perf_counter()
    # print(type(numpy_image))
    # print(numpy_image)
    # print(numpy_image.dtype)
    # print(numpy_image.shape)
    # print(numpy_image.sum(axis=0).shape)
    # print(numpy_image.sum(axis=1).shape)
    if numpy_image is None:
        logger.warning("Failed to get numpy array from RawImage")
        return
    # logger.debug(f"Frame Content: \n{numpy_image}")

    if hasattr(camera_device_dh, "device_driver"):

        roi_x_start = camera_device_dh.device_driver.getParam("ROI_X_START")
        roi_y_start = camera_device_dh.device_driver.getParam("ROI_Y_START")

        roi_x_axis = np.arange(roi_x_start, roi_x_start + ROI_WIDTH)
        roi_y_axis = np.arange(roi_y_start, roi_y_start + ROI_HEIGHT)

        pixel_length = camera_device_dh.device_driver.getParam("PIXEL_LENGTH")

        roi_image = numpy_image[
            roi_y_start : roi_y_start + ROI_HEIGHT,
            roi_x_start : roi_x_start + ROI_WIDTH,
        ]

        roi_x_data = roi_image.sum(axis=0, dtype=np.float64)
        roi_y_data = roi_image.sum(axis=1, dtype=np.float64)
        roi_x_data_max_pos = np.argmax(roi_x_data)
        roi_x_data_max = roi_x_data[roi_x_data_max_pos]
        roi_y_data_max_pos = np.argmax(roi_y_data)
        roi_y_data_max = roi_y_data[roi_y_data_max_pos]

        p0_x = [
            roi_x_data_max,
            roi_x_axis[roi_x_data_max_pos],
            np.std(roi_x_data),
        ]
        p0_y = [
            roi_y_data_max,
            roi_y_axis[roi_y_data_max_pos],
            np.std(roi_y_data),
        ]

        if camera_device_dh.performance_stat:
            start_fit_time = time.perf_counter()
        try:
            popt_x, pcov_x = curve_fit(
                gaussian,
                roi_x_axis,
                roi_x_data,
                p0=p0_x,
                method="lm",
                maxfev=ITERATION_LIMIT,
            )
            popt_y, pcov_y = curve_fit(
                gaussian,
                roi_y_axis,
                roi_y_data,
                p0=p0_y,
                method="lm",
                maxfev=ITERATION_LIMIT,
            )
        except RuntimeError as e:
            if camera_device_dh.result_stat:
                result_stat("RuntimeError")
            popt_x = [0, 0, 0]
            popt_y = [0, 0, 0]
        except Exception as e:
            if camera_device_dh.result_stat:
                result_stat("Others")
            popt_x = [0, 0, 0]
            popt_y = [0, 0, 0]
        else:
            if camera_device_dh.result_stat:
                result_stat("Success")
        if camera_device_dh.performance_stat:
            end_fit_time = time.perf_counter()
            fit_stat(end_fit_time - start_fit_time)

        max_x, pos_x, sigma_x = popt_x
        max_y, pos_y, sigma_y = popt_y

        roi_x_fit_data = gaussian(roi_x_axis, *popt_x)
        roi_y_fit_data = gaussian(roi_y_axis, *popt_y)

        if camera_device_dh.performance_stat:
            start_update_time = time.perf_counter()
        with handle_lock:
            camera_device_dh.device_driver.setParam("FRAME_ID", frame_id)
            camera_device_dh.device_driver.setParam("IMAGE", numpy_image.ravel())
            camera_device_dh.device_driver.setParam("ROI_IMAGE", roi_image.ravel())
            camera_device_dh.device_driver.setParam("ROI_X_DATA", roi_x_data)
            camera_device_dh.device_driver.setParam("ROI_Y_DATA", roi_y_data)
            camera_device_dh.device_driver.setParam("ROI_X_FIT_DATA", roi_x_fit_data)
            camera_device_dh.device_driver.setParam("ROI_Y_FIT_DATA", roi_y_fit_data)
            camera_device_dh.device_driver.setParam("ROI_X_FIT_MAX", max_x)
            camera_device_dh.device_driver.setParam("ROI_X_FIT_POS", pos_x)
            camera_device_dh.device_driver.setParam(
                "ROI_X_FIT_POS_LEN", pos_x * pixel_length
            )
            camera_device_dh.device_driver.setParam("ROI_X_FIT_SIGMA", sigma_x)
            camera_device_dh.device_driver.setParam("ROI_Y_FIT_MAX", max_y)
            camera_device_dh.device_driver.setParam("ROI_Y_FIT_POS", pos_y)
            camera_device_dh.device_driver.setParam(
                "ROI_Y_FIT_POS_LEN", pos_y * pixel_length
            )
            camera_device_dh.device_driver.setParam("ROI_Y_FIT_SIGMA", sigma_y)
            camera_device_dh.device_driver.updatePVs()
        if camera_device_dh.performance_stat:
            end_update_time = time.perf_counter()
            update_stat(end_update_time - start_update_time)
    else:
        logger.error("device driver not found")

    if camera_device_dh.performance_stat:
        end_handle_time = time.perf_counter()
        handle_stat(end_handle_time - start_handle_time)


if __name__ == "__main__":
    camera = CameraDeviceDH("test", "192.168.1.200")
    camera.list_pvs()
