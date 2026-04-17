import sys
import time
import threading
from datetime import datetime
from epics import caget, camonitor, poll, PV

statistics_count = 0
statistics_dict = {}
statistics_lock = threading.Lock()


def do_statistics():
    print("统计结果:")
    length = len(statistics_dict)
    start_time = statistics_dict[1]["time"]
    end_time = statistics_dict[length - 1]["time"]
    frame_rate = (length - 1) / (end_time - start_time)
    print(f"帧率: {frame_rate:.2f}")


def value_callback(**kw):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print("time: ", now)
    print("kw: ", kw)


def image_callback(pvname, value, **kw):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print("time: ", now, " pvname: ", pvname, " value length: ", len(value))
    print("value: ", value)


def image_statistics_callback(pvname, value, **kw):
    global statistics_count, statistics_dict
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(
        "count",
        statistics_count,
        "\ttime:",
        now,
        "\tpvname:",
        pvname,
        "\tlength:",
        len(value),
    )
    with statistics_lock:
        statistics_dict[statistics_count] = {
            "time": time.perf_counter(),
            "pvname": pvname,
            "value": value,
            "kwargs": kw,
        }
        statistics_count += 1


pv_name = "IMAGE"
pv = PV(pv_name, auto_monitor=True, callback=image_statistics_callback)
pv.wait_for_connection(timeout=3)
print("PV:", pv_name)
print("connected:", pv.connected)


time.sleep(1)
if pv.connected:
    print(
        "Ready for test start (press Ctrl-C to get statistics report and exit when test finished)"
    )
else:
    print("Failed to connect to test PV")
    sys.exit(1)

# camonitor("FrameID", callback=value_callback)

while True:
    try:
        poll()
    except KeyboardInterrupt:
        do_statistics()
        break
