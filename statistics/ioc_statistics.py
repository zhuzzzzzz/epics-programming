#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IOC 统计分析脚本

此脚本用于分析 EPICS IOC 的运行时信息和性能指标。
它从 info 文件中收集 PV 数量，并从 Prometheus 中检索性能指标，
然后对资源利用率进行统计分析。
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import requests
import math
import matplotlib.pyplot as plt
import numpy as np


# 全局配置变量
# 需要分析的 IOC 名称列表
IOC_LIST = []

PROMETHEUS_URL = (
    "http://192.168.20.169:9090/api/v1/query_range"  # Prometheus API 接口地址
)
PROMETHEUS_INSTANT_URL = (
    "http://192.168.20.169:9090/api/v1/query"  # Prometheus 即时查询 API 接口地址
)

# IOC 名称前缀，用于过滤 Prometheus 查询结果
IOC_PREFIX = "dals_srv-"

# 按数据类型分组的指标字典，便于更好地组织
METRICS_DICT = {
    "cpu": "container_cpu_core_usage_percent:name_service_instance",
    "memory_percentage": "container_memory_usage_percent:name_service_instance",
}  # 按数据类型分组的指标字典

# 添加新的指标字典，用于存储转换后的 MiB 值
ADDITIONAL_METRICS_DICT = {
    "memory_mib": "memory_percentage"  # 基于 memory_percentage 转换为 MiB
}

TIME_RANGE_HOURS = 24 * 28  # 分析时间范围（小时）

PV_FILES_PARENT_DIR = (
    "C:\\Users\\zhu\\Desktop\\swarm"  # 包含 IOC 子目录和 PV info 文件的父目录
)

# Prometheus 查询步长（秒）
QUERY_STEP = "3600s"

# 内存上限（MiB）- 假设系统内存上限为 1 GiB
MEMORY_LIMIT_MIB = 1024.0


def get_ioc_list_from_prometheus() -> List[str]:
    """
    从 Prometheus 查询 IOC 列表

    返回:
        IOC 名称列表
    """
    print("正在从 Prometheus 自动获取 IOC 列表...")

    # 构造查询语句，查询 container_cpu_core_usage_percent 指标中 service_type 为 ioc 的实例
    query = 'container_last_beat_seconds:name_service_instance{service_type="ioc"}'

    # 准备查询参数
    params = {"query": query}

    try:
        # 向 Prometheus 发起即时查询请求
        response = requests.get(PROMETHEUS_INSTANT_URL, params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                # 从结果中提取 IOC 名称
                ioc_names = set()
                results = data.get("data", {}).get("result", [])
                for result in results:
                    metric = result.get("metric", {})
                    # 从 service 标签获取 IOC 名称
                    ioc_name = metric.get("service")
                    if ioc_name:
                        # 如果设置了前缀，移除前缀
                        if IOC_PREFIX and ioc_name.startswith(IOC_PREFIX):
                            ioc_name = ioc_name[len(IOC_PREFIX) :]
                        ioc_names.add(ioc_name)

                ioc_list = sorted(list(ioc_names))
                print(f"从 Prometheus 检测到 {len(ioc_list)} 个 IOC: {ioc_list}")
                return ioc_list
            else:
                print(f"Prometheus 查询失败: {data.get('error', '未知错误')}")
                return []
        else:
            print(
                f"Prometheus 查询失败，状态码 {response.status_code}: {response.text}"
            )
            return []
    except Exception as e:
        print(f"查询 Prometheus IOC 列表出错: {e}")
        return []


def get_ioc_list() -> List[str]:
    """
    获取 IOC 列表

    返回:
        IOC 名称列表
    """
    global IOC_LIST

    # 如果全局 IOC_LIST 为空，则从 Prometheus 获取并更新全局变量
    if not IOC_LIST:
        IOC_LIST = get_ioc_list_from_prometheus()

    return IOC_LIST


def get_pv_counts() -> Dict[str, int]:
    """
    通过读取 .info 文件统计每个 IOC 的 PV 数量

    返回:
        字典，将 IOC 名称映射到其 PV 数量
    """
    # 获取 IOC 列表
    ioc_list = get_ioc_list()

    pv_counts = {}

    for ioc_name in ioc_list:
        # 构造 .info 文件的路径
        info_file_path = os.path.join(
            PV_FILES_PARENT_DIR, ioc_name, "logs", f"{ioc_name}.info"
        )

        # 检查文件是否存在
        if os.path.exists(info_file_path):
            try:
                with open(info_file_path, "r", encoding="utf-8") as f:
                    # 查找 #pv list 部分并统计条目数量
                    pv_count = 0
                    in_pv_section = False

                    for line in f:
                        line = line.strip()

                        # 检查是否进入 PV 列表部分
                        if line == "#pv list":
                            in_pv_section = True
                            continue

                        # 检查是否离开 PV 列表部分
                        if (
                            line.startswith("#")
                            and in_pv_section
                            and line != "#pv list"
                        ):
                            in_pv_section = False
                            continue

                        # 如果在 PV 列表部分且行不为空，则计数
                        if in_pv_section and line:
                            pv_count += 1

                    pv_counts[ioc_name] = pv_count
            except Exception as e:
                print(f"读取 {info_file_path} 出错: {e}")
                pv_counts[ioc_name] = 0
        else:
            print(f"未找到 {ioc_name} 的 info 文件: {info_file_path}")
            pv_counts[ioc_name] = 0

    return pv_counts


def get_all_metrics() -> Dict[str, str]:
    """
    获取指标字典

    返回:
        指标字典
    """
    return METRICS_DICT


def query_prometheus(metric_name: str, hours: int) -> Dict:
    """
    查询 Prometheus 在一段时间范围内的特定指标

    参数:
        metric_name: 要查询的指标名称
        hours: 时间范围（小时）

    返回:
        Prometheus API 响应字典
    """
    # 计算时间范围
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)

    # 格式化时间为 Prometheus 格式
    start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # 准备查询参数
    params = {
        "query": f'{metric_name}{{service_type="ioc"}}',
        "start": start_str,
        "end": end_str,
        "step": QUERY_STEP,
    }

    try:
        # 向 Prometheus 发起请求
        response = requests.get(PROMETHEUS_URL, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(
                f"Prometheus 查询失败，状态码 {response.status_code}: {response.text}"
            )
            return {}
    except Exception as e:
        print(f"查询 Prometheus 指标 {metric_name} 出错: {e}")
        return {}


def linear_regression(
    x_values: List[float], y_values: List[float]
) -> Tuple[float, float, float]:
    """
    计算线性回归 y = a + bx 和相关系数

    参数:
        x_values: x 值列表（如 PV 数量）
        y_values: y 值列表（如指标平均值）

    返回:
        (截距 a, 斜率 b, 相关系数 r)
    """
    n = len(x_values)
    if n < 2:
        return 0.0, 0.0, 0.0

    # 计算均值
    mean_x = sum(x_values) / n
    mean_y = sum(y_values) / n

    # 计算回归系数
    numerator = sum((x_values[i] - mean_x) * (y_values[i] - mean_y) for i in range(n))
    denominator_x = sum((x_values[i] - mean_x) ** 2 for i in range(n))
    denominator_y = sum((y_values[i] - mean_y) ** 2 for i in range(n))

    if denominator_x == 0 or denominator_y == 0:
        return mean_y, 0.0, 0.0

    # 计算斜率和截距
    slope = numerator / denominator_x
    intercept = mean_y - slope * mean_x

    # 计算相关系数
    correlation = numerator / math.sqrt(denominator_x * denominator_y)

    return intercept, slope, correlation


def analyze_metrics(metrics_data: Dict, pv_counts: Dict[str, int]) -> Dict:
    """
    分析指标数据并计算统计数据

    参数:
        metrics_data: 来自 Prometheus 的指标数据字典，以指标类别为键
        pv_counts: 每个 IOC 的 PV 数量字典

    返回:
        分析后的统计数据字典，使用 METRICS_DICT 的键作为主键
    """
    if not metrics_data or not isinstance(metrics_data, dict):
        return {}

    results = {}
    total_pvs = sum(pv_counts.values())

    # 直接遍历 METRICS_DICT 来处理指标
    for category in metrics_data:

        metric_result = metrics_data[category]

        # 检查数据有效性
        if not metric_result or not isinstance(metric_result, dict):
            continue

        if not metric_result.get("data", {}).get("result"):
            continue

        # 初始化统计数据容器
        ioc_stats = {}

        # 处理每个时间序列
        for series in metric_result["data"]["result"]:
            # 从指标标签中提取 IOC 名称
            metric_labels = series.get("metric", {})
            ioc_name = metric_labels.get("service", "unknown")
            if IOC_PREFIX and ioc_name.startswith(IOC_PREFIX):
                ioc_name = ioc_name.removeprefix(IOC_PREFIX)

            # 提取值
            values = series.get("values", [])
            if not values:
                continue

            # 将字符串值转换为浮点数
            numeric_values = [float(v[1]) for v in values]

            # 计算此 IOC 的统计数据
            if numeric_values:
                avg_value = sum(numeric_values) / len(numeric_values)
                max_value = max(numeric_values)
                min_value = min(numeric_values)

                ioc_stats[ioc_name] = {
                    "avg": avg_value,
                    "max": max_value,
                    "min": min_value,
                    "count": len(numeric_values),
                    "raw_data": values,  # 保存原始数据用于绘图等用途
                }

        # 只有当我们有有效的统计数据时才继续
        if not ioc_stats:
            continue

        # 计算整体统计数据
        # 收集所有数值用于整体统计计算
        all_numeric_values = []
        for ioc_name, stats in ioc_stats.items():
            # 收集每个IOC的数值，重复次数等于该IOC的数据点数
            all_numeric_values.extend([stats["avg"]] * stats["count"])

        overall_avg = (
            sum(all_numeric_values) / len(all_numeric_values)
            if all_numeric_values
            else 0
        )
        overall_max = max(all_numeric_values) if all_numeric_values else 0
        overall_min = min(all_numeric_values) if all_numeric_values else 0

        # 按 PV 计算（所有IOC总计的指标与所有PV数量的比值）
        per_pv_total = overall_avg / total_pvs if total_pvs > 0 else 0

        # 单个 IOC 按 PV 计算（单个IOC的指标平均值与该IOC的PV数量的比值）
        per_ioc_per_pv = {}
        for ioc_name, stats in ioc_stats.items():
            ioc_pv_count = pv_counts.get(ioc_name, 0)
            per_ioc_per_pv[ioc_name] = (
                stats["avg"] / ioc_pv_count if ioc_pv_count > 0 else 0
            )

        # 线性回归分析：指标值与 PV 数量的关系
        x_values = []  # PV 数量
        y_values = []  # 指标平均值

        for ioc_name, stats in ioc_stats.items():
            ioc_pv_count = pv_counts.get(ioc_name, 0)
            if ioc_pv_count > 0:
                x_values.append(float(ioc_pv_count))
                y_values.append(stats["avg"])

        # 计算线性回归参数
        intercept, slope, correlation = (
            linear_regression(x_values, y_values)
            if x_values and y_values
            else (0.0, 0.0, 0.0)
        )

        results[category] = {
            "overall": {"avg": overall_avg, "max": overall_max, "min": overall_min},
            "per_pv_total": per_pv_total,
            "ioc_stats": ioc_stats,
            "per_ioc_per_pv": per_ioc_per_pv,
            "linear_regression": {
                "intercept": intercept,  # 截距（固定开销）
                "slope": slope,  # 斜率（每个 PV 的开销）
                "correlation": correlation,  # 相关系数（线性关系符合程度）
            },
            "metrics_name": metrics_data[category]['data']['result'][0]['metric']['__name__']
        }

    return results


def query_all_metrics(hours: int) -> Dict:
    """
    查询所有指标从 Prometheus

    参数:
        hours: 时间范围（小时）

    返回:
        包含所有指标数据的字典，以指标名称为键
    """
    all_metrics = {}

    # 获取指标字典
    metrics_dict = get_all_metrics()

    for category, metric in metrics_dict.items():
        print(f"正在查询 Prometheus 指标 {metric}...")
        data = query_prometheus(metric, hours)
        if data and data.get("status") == "success":
            # 使用指标名称作为键
            all_metrics[category] = data
        else:
            print(f"未收到指标 {metric} 的数据")

    # 处理额外的指标转换（例如从百分比转换为 MiB）
    # 这里我们需要基于已有的指标计算新指标
    if "memory_percentage" in all_metrics:
        print("正在转换内存使用率从百分比到 MiB...")
        # 复制 memory_percentage 数据作为基础
        memory_mib_data = json.loads(json.dumps(all_metrics["memory_percentage"]))

        # 转换所有数值从百分比到 MiB
        for series in memory_mib_data.get("data", {}).get("result", []):
            values = series.get("values", [])
            for i in range(len(values)):
                # 转换百分比值为 MiB 值
                values[i][1] = str(float(values[i][1]) * MEMORY_LIMIT_MIB / 100.0)

        # 添加到结果中
        all_metrics["memory_mib"] = memory_mib_data

    return all_metrics


def print_statistics(pv_counts: Dict[str, int], metrics_stats: Dict):
    """
    打印格式化的统计数据

    参数:
        pv_counts: 每个 IOC 的 PV 数量字典
        metrics_stats: 分析后的指标统计数据字典，使用 METRICS_DICT 的键作为主键
    """
    total_pvs = sum(pv_counts.values())

    print("\n" + "=" * 60)
    print("IOC 统计报告")
    print("=" * 60)

    print(f"\n所有 IOC 的 PV 总数: {total_pvs}")
    print("\n各 IOC 的 PV 数量:")
    print("-" * 30)
    for ioc, count in pv_counts.items():
        print(f"{ioc:>20}: {count:>6} 个 PV")

    print("\n资源利用统计:")
    print("-" * 60)

    # 检查是否有统计数据
    if not metrics_stats:
        print("未获取到任何资源利用统计数据")
        return

    # 遍历 METRICS_DICT 中的类别
    for category in metrics_stats.keys():
        stats = metrics_stats[category]
        print(f"\n类别: {category.upper()}")
        print("-" * 40)

        # 显示正确的指标名称和单位
        display_metric_name = stats['metrics_name']
        unit = ""
        if category == "cpu":
            unit = " (%)"
        elif category == "memory_percentage":
            unit = " (%)"
        elif category == "memory_mib":
            unit = " (MiB)"

        print(f"指标: {display_metric_name}")
        print(f"  整体平均值{unit}: {stats['overall']['avg']:.4f}")
        print(f"  整体最大值{unit}: {stats['overall']['max']:.4f}")
        print(f"  整体最小值{unit}: {stats['overall']['min']:.4f}")
        print(f"  每 PV 平均值（总计）{unit}: {stats['per_pv_total']:.6f}")

        # 线性回归分析结果（如果存在）
        if "linear_regression" in stats:
            lin_reg = stats["linear_regression"]
            print(f"\n  线性回归分析 (y = a + bx):")
            print(f"    固定开销 (截距 a){unit}: {lin_reg['intercept']:.6f}")
            print(f"    每 PV 开销 (斜率 b){unit}: {lin_reg['slope']:.4f}")
            print(f"    相关系数 (r): {lin_reg['correlation']:.4f}")
            print(f"    决定系数 (r²): {lin_reg['correlation']**2:.4f}")

            # 线性关系符合程度判断
            r_squared = lin_reg["correlation"] ** 2
            if r_squared > 0.7:
                fit_desc = "强线性关系"
            elif r_squared > 0.4:
                fit_desc = "中等线性关系"
            elif r_squared > 0.2:
                fit_desc = "弱线性关系"
            else:
                fit_desc = "无线性关系"

            print(f"    线性关系符合程度: {fit_desc}")

            # 绘制线性关系图
            plot_linear_regression(category, pv_counts, stats)

        print("\n  各 IOC 详细指标情况:")
        header_format = (
            "  "
            + "IOC 名称".ljust(20)
            + "PV 数量".ljust(10)
            + f"平均值{unit}".ljust(15)
            + f"最大值{unit}".ljust(15)
            + f"最小值{unit}".ljust(15)
            + f"每 PV 平均值{unit}".ljust(15)
        )
        print(header_format)
        print("  " + "-" * 95)
        for ioc_name, ioc_stat in stats["ioc_stats"].items():
            ioc_pv_count = pv_counts.get(ioc_name, 0)
            per_pv_avg = (
                stats["per_ioc_per_pv"].get(ioc_name, 0)
                if "per_ioc_per_pv" in stats
                else 0
            )
            stat_format = (
                f"  {{:<20}}{{:<10}}{{:<15.4f}}{{:<15.4f}}{{:<15.4f}}{{:<15.6f}}"
            )
            print(
                stat_format.format(
                    ioc_name,
                    ioc_pv_count,
                    ioc_stat["avg"],
                    ioc_stat["max"],
                    ioc_stat["min"],
                    per_pv_avg,
                )
            )


def plot_linear_regression(category: str, pv_counts: Dict[str, int], stats: Dict):
    """
    绘制线性关系图

    参数:
        category: 指标类别 (如 'cpu', 'memory')
        pv_counts: 每个 IOC 的 PV 数量字典
        stats: 指标统计数据
    """
    # 准备数据
    x_values = []  # PV 数量
    y_values = []  # 指标平均值
    labels = []  # IOC 名称

    for ioc_name, ioc_stat in stats["ioc_stats"].items():
        ioc_pv_count = pv_counts.get(ioc_name, 0)
        if ioc_pv_count > 0:
            x_values.append(ioc_pv_count)
            y_values.append(ioc_stat["avg"])
            labels.append(ioc_name)

    if not x_values:
        print("    无可视化数据")
        return

    # 创建图表
    plt.figure(figsize=(10, 6))

    # 绘制散点图
    plt.scatter(x_values, y_values, alpha=0.7, s=50)

    # 标注点
    for i, label in enumerate(labels):
        plt.annotate(
            label,
            (x_values[i], y_values[i]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
            alpha=0.7,
        )

    # 绘制回归线
    lin_reg = stats["linear_regression"]
    if lin_reg["slope"] != 0 or lin_reg["intercept"] != 0:
        x_line = np.linspace(min(x_values), max(x_values), 100)
        y_line = lin_reg["intercept"] + lin_reg["slope"] * x_line
        r_squared = lin_reg["correlation"] ** 2
        plt.plot(
            x_line,
            y_line,
            "r-",
            label=f'y={lin_reg["intercept"]:.4f}+{lin_reg["slope"]:.4f}x (R²={r_squared:.4f})',
        )

    # 图表设置
    plt.xlabel("PV Count")

    # 设置 Y 轴标签和图表标题的单位
    ylabel = "Metric Average"
    title = f"Linear Regression - {category.upper()}"
    if category == "memory_percentage":
        ylabel = "Memory Usage (%)"
        title = f"Linear Regression - MEMORY (%)"
    elif category == "memory_mib":
        ylabel = "Memory Usage (MiB)"
        title = f"Linear Regression - MEMORY (MiB)"
    elif category == "cpu":
        ylabel = "CPU Usage (%)"
        title = f"Linear Regression - CPU (%)"

    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.grid(True, alpha=0.3)

    # 保存图片
    filename = f"{category}_linear_regression.png"
    plt.savefig(filename, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"    线性关系图已保存为: {filename}")


def main():
    """
    主函数，运行 IOC 统计分析
    """
    print("开始 IOC 统计分析...")

    # 获取所有 IOC 的 PV 数量
    print("正在收集 PV 数量...")
    pv_counts = get_pv_counts()

    # 从 Prometheus 查询指标
    print("正在查询 Prometheus 指标...")
    metrics_data = query_all_metrics(TIME_RANGE_HOURS)

    # 分析指标
    print("正在分析指标...")
    metrics_stats = analyze_metrics(metrics_data, pv_counts)

    # 打印结果
    print_statistics(pv_counts, metrics_stats)

    print("\n分析完成。")


if __name__ == "__main__":
    main()
