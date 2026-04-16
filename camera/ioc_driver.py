import logging
import threading
import time
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from epics_device import EpicsDevice
from pcaspy import Driver, Severity, Alarm


logger = logging.getLogger(__name__)


class IOCDriver(Driver):
    def __init__(
        self,
        device: EpicsDevice,
        update_interval=3.0,
        detect_interval=3.0,
        reconnect_interval=30.0,
    ):
        Driver.__init__(self)
        #
        self._device = device
        self._device.device_driver = self
        self._executor = ThreadPoolExecutor()
        self._process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._lock = threading.Lock()
        self._write_lock = {}
        self._status_normal = True
        self.update_interval = update_interval
        self.detect_interval = detect_interval
        self.reconnect_interval = reconnect_interval
        #
        self._process_thread.start()
        self._update_thread.start()

    def __del__(self):
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=True)

    # 不建议使用scan配合read方法
    # 1. 当read方法阻塞, 对应的PV会被卡住, 此期间内该PV无法更新
    # 2. 当设备读取失败, 此时不得不调用父类方法, 此时依然会获取到前值并强制更新PV的值和状态, 与内部的扫描更新逻辑冲突
    # 应自己实现设备属性周期性更新逻辑
    # def read(self, reason):
    #     try:
    #         while True:
    #             if self._status_normal:
    #                 break
    #         val = self._device.get_attr(reason)
    #         if val is not None:
    #             return val
    #         return super().read(reason)
    #     except Exception as e:
    #         print(f"read error: {e}")

    def set_pv_value(self, reason, value, lock=None):
        logger.debug(f'update PV "{reason}"(value={repr(value)})')
        if hasattr(lock, "acquire") and hasattr(lock, "release"):
            try:
                self.setParam(reason, value)
                self.callbackPV(reason)
                self.updatePV(reason)
            finally:
                lock.release()
        else:
            with self._lock:
                lock_temp = self._write_lock.setdefault(reason, threading.Lock())
            with lock_temp:
                self.setParam(reason, value)
                self.callbackPV(reason)
                self.updatePV(reason)

    def set_pv_status(self, reason, alarm, severity, lock=None):
        logger.debug(f'update PV "{reason}"(alarm={repr(alarm)}, severity={repr(severity)})')
        if hasattr(lock, "acquire") and hasattr(lock, "release"):
            try:
                self.setParamStatus(
                    reason,
                    alarm=alarm,
                    severity=severity,
                )
                self.updatePV(reason)
            finally:
                lock.release()
        else:
            with self._lock:
                lock_temp = self._write_lock.setdefault(reason, threading.Lock())
            with lock_temp:
                self.setParamStatus(
                    reason,
                    alarm=alarm,
                    severity=severity,
                )
                self.updatePV(reason)

    def write(self, reason, value):
        with self._lock:
            lock_temp = self._write_lock.setdefault(reason, threading.Lock())
        if not lock_temp.acquire(blocking=False):
            logger.warning(
                f'write failed(set "{reason}" to {repr(value)}): "{reason}" is currently locked by another write thread'
            )
            return False
        try:
            future = self._executor.submit(self._device.set_attr, reason, value)
            future.add_done_callback(
                partial(
                    self._write_callback, reason=reason, value=value, lock=lock_temp
                )
            )
        except Exception:
            logger.exception(
                f'failed to start write thread(set "{reason}" to {repr(value)})'
            )
            return False
        else:
            return True

    def _write_callback(self, future, reason, value, lock):
        res = future.result()
        if res is True:
            # write success, update PV
            self.set_pv_value(reason, value, lock=lock)
        elif res is False:
            # write failed, do not update PV
            self.callbackPV(reason)
            lock.release()
        elif res is None:
            # write operation not supported, may be a soft PV, update as normal
            self.set_pv_value(reason, value, lock=lock)

    def _process_loop(self):
        while True:
            # detection loop
            while True:
                logger.debug("in detection loop")
                if not self._device.is_connected():
                    self._status_normal = False
                    logger.error(f"device disconnection detected")
                    self._set_all_invalid()
                    break
                else:
                    time.sleep(self.detect_interval)
            # reconnection loop
            while True:
                logger.warning(f"try reconnecting")
                try:
                    self._device.reconnect()
                except Exception as e:
                    logger.error(f"reconnect failed: {e}")
                    time.sleep(self.reconnect_interval)
                    continue
                if self._device.is_connected():
                    self._status_normal = True
                    logger.info(f"device reconnected")
                    break
                else:
                    logger.warning(f"device still disconnected")

    def _update_loop(self):
        while True:
            if not self._status_normal:
                logger.debug("update loop stopped as in abnormal status")
                time.sleep(self.update_interval)
                continue
            logger.debug(f"updating all PVs from device")
            try:
                for pv_base in self._device.PV_DB.keys():
                    logger.debug(f'update PV "{pv_base}"')
                    reason = pv_base
                    with self._lock:
                        lock_temp = self._write_lock.setdefault(
                            reason, threading.Lock()
                        )
                    with lock_temp:
                        value = self._device.get_attr(pv_base)
                        if value is not None:
                            self.setParam(pv_base, value)
                else:
                    self.updatePVs()
            finally:
                time.sleep(self.update_interval)

    def _set_all_invalid(self):
        logger.warning("set all PVs invalid")
        for pv_base in self._device.PV_DB.keys():
            reason = pv_base
            with self._lock:
                lock_temp = self._write_lock.setdefault(reason, threading.Lock())
            with lock_temp:
                self.setParamStatus(
                    pv_base,
                    alarm=Alarm.LINK_ALARM,
                    severity=Severity.INVALID_ALARM,
                )
        else:
            self.updatePVs()
