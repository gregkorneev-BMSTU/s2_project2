import csv
import os

import numpy as np

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ModuleNotFoundError:
    import cv2

    HAS_MATPLOTLIB = False


RESULTS_DIR = os.path.join("results", "python")
DEBUG_DIR = os.path.join(RESULTS_DIR, "debug")
UPPER_POINTS_PATH = os.path.join(DEBUG_DIR, "upper_points.csv")
LOWER_POINTS_PATH = os.path.join(DEBUG_DIR, "lower_points.csv")
RESULT_CSV_PATH = os.path.join(RESULTS_DIR, "result.csv")
FHR_PLOT_PATH = os.path.join(DEBUG_DIR, "calibrated_fhr_plot.png")
UA_PLOT_PATH = os.path.join(DEBUG_DIR, "calibrated_ua_plot.png")

# TODO: уточнить x-координаты временных меток по исходному изображению.
TIME_MARKS = [
    (216.0, "09:04:38"),
    (795.0, "09:08:38"),
    (1374.0, "09:12:38"),
    (1953.0, "09:16:38"),
]

# TODO: уточнить y-координаты шкалы FHR по линиям 200 и 60 bpm.
FHR_TOP_Y = 300.0
FHR_BOTTOM_Y = 1020.0
FHR_TOP_VALUE = 200.0
FHR_BOTTOM_VALUE = 60.0

# TODO: уточнить y-координаты шкалы UA по линиям 12 и 0 kPa.
UA_TOP_Y = 90.0
UA_BOTTOM_Y = 657.0
UA_TOP_KPA = 12.0
UA_BOTTOM_KPA = 0.0
KPA_TO_MMHG = 7.50062


def load_trace_csv(path):
    """Загружает CSV с колонками x_px,y_px в массив Nx2."""
    rows = []

    with open(path, "r", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            rows.append((float(row["x_px"]), float(row["y_px"])))

    if len(rows) == 0:
        return np.empty((0, 2), dtype=np.float64)

    return np.array(rows, dtype=np.float64)


def parse_time_string(time_str):
    """Переводит HH:MM:SS в секунды от начала суток."""
    parts = time_str.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid time string: {time_str}")

    hours, minutes, seconds = [int(part) for part in parts]
    return hours * 3600 + minutes * 60 + seconds


def compute_seconds_per_pixel(time_marks=TIME_MARKS):
    """Вычисляет x0 и seconds_per_pixel по ручным временным меткам."""
    if len(time_marks) < 2:
        raise ValueError("At least two time marks are required")

    sorted_marks = sorted(time_marks, key=lambda item: item[0])
    x_values = np.array([mark[0] for mark in sorted_marks], dtype=np.float64)
    raw_seconds = [parse_time_string(mark[1]) for mark in sorted_marks]
    unwrapped_seconds = [float(raw_seconds[0])]

    for seconds in raw_seconds[1:]:
        value = float(seconds)
        while value < unwrapped_seconds[-1]:
            value += 24.0 * 60.0 * 60.0
        unwrapped_seconds.append(value)

    elapsed_seconds = np.array(unwrapped_seconds, dtype=np.float64)
    elapsed_seconds -= elapsed_seconds[0]

    seconds_per_pixel, intercept = np.polyfit(x_values, elapsed_seconds, 1)
    if seconds_per_pixel <= 0:
        raise ValueError("Time marks must produce a positive seconds_per_pixel")

    x0 = -intercept / seconds_per_pixel
    return x0, seconds_per_pixel


def pixel_to_fhr(y):
    """Линейно переводит y верхней панели в FHR bpm."""
    scale = (FHR_BOTTOM_VALUE - FHR_TOP_VALUE) / (FHR_BOTTOM_Y - FHR_TOP_Y)
    return FHR_TOP_VALUE + (np.asarray(y, dtype=np.float64) - FHR_TOP_Y) * scale


def pixel_to_ua_kpa(y):
    """Линейно переводит y нижней панели в UA kPa."""
    scale = (UA_BOTTOM_KPA - UA_TOP_KPA) / (UA_BOTTOM_Y - UA_TOP_Y)
    return UA_TOP_KPA + (np.asarray(y, dtype=np.float64) - UA_TOP_Y) * scale


def pixel_to_ua_mmhg(kpa):
    """Переводит UA из kPa в mmHg."""
    return np.asarray(kpa, dtype=np.float64) * KPA_TO_MMHG


def calibrate_trace(points, x0, seconds_per_pixel, value_converter):
    """Переводит пиксельный ряд Nx2 в колонки time_sec,value."""
    calibrated = np.empty((points.shape[0], 2), dtype=np.float64)
    calibrated[:, 0] = (points[:, 0] - x0) * seconds_per_pixel
    calibrated[:, 1] = value_converter(points[:, 1])
    return calibrated


def merge_timeseries(fhr_trace, ua_trace):
    """Объединяет FHR и UA по имеющимся временным точкам без интерполяции."""
    rows_by_time = {}

    for time_sec, fhr_bpm in fhr_trace:
        time_key = round(float(time_sec), 6)
        rows_by_time.setdefault(
            time_key,
            {
                "time_sec": float(time_sec),
                "fhr_bpm": np.nan,
                "ua_kpa": np.nan,
                "ua_mmhg": np.nan,
            },
        )
        rows_by_time[time_key]["fhr_bpm"] = float(fhr_bpm)

    for time_sec, ua_kpa in ua_trace:
        time_key = round(float(time_sec), 6)
        rows_by_time.setdefault(
            time_key,
            {
                "time_sec": float(time_sec),
                "fhr_bpm": np.nan,
                "ua_kpa": np.nan,
                "ua_mmhg": np.nan,
            },
        )
        rows_by_time[time_key]["ua_kpa"] = float(ua_kpa)
        rows_by_time[time_key]["ua_mmhg"] = float(pixel_to_ua_mmhg(ua_kpa))

    merged_rows = []
    for sample_idx, time_key in enumerate(sorted(rows_by_time)):
        row = rows_by_time[time_key]
        merged_rows.append(
            {
                "sample_idx": sample_idx,
                "time_sec": row["time_sec"],
                "fhr_bpm": row["fhr_bpm"],
                "ua_kpa": row["ua_kpa"],
                "ua_mmhg": row["ua_mmhg"],
            }
        )

    return merged_rows


def save_final_csv(path, rows):
    """Сохраняет финальный физический ряд."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fieldnames = ["sample_idx", "time_sec", "fhr_bpm", "ua_kpa", "ua_mmhg"]

    with open(path, "w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "sample_idx": row["sample_idx"],
                    "time_sec": _format_float(row["time_sec"]),
                    "fhr_bpm": _format_float(row["fhr_bpm"]),
                    "ua_kpa": _format_float(row["ua_kpa"]),
                    "ua_mmhg": _format_float(row["ua_mmhg"]),
                }
            )


def save_debug_plot(path, trace, y_label, title):
    """Сохраняет простой debug-график откалиброванного ряда."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if not HAS_MATPLOTLIB:
        save_debug_plot_cv2(path, trace, y_label, title)
        return

    plt.figure(figsize=(12, 4))
    plt.plot(trace[:, 0], trace[:, 1], linewidth=1.0)
    plt.xlabel("time_sec")
    plt.ylabel(y_label)
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def save_debug_plot_cv2(path, trace, y_label, title):
    """Fallback-график, если matplotlib не установлен в окружении."""
    width = 1200
    height = 420
    margin_left = 80
    margin_right = 30
    margin_top = 45
    margin_bottom = 55
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    image = np.full((height, width, 3), 255, dtype=np.uint8)

    cv2.rectangle(
        image,
        (margin_left, margin_top),
        (margin_left + plot_width, margin_top + plot_height),
        (40, 40, 40),
        1,
    )

    for index in range(1, 5):
        x = margin_left + int(plot_width * index / 5)
        y = margin_top + int(plot_height * index / 5)
        cv2.line(image, (x, margin_top), (x, margin_top + plot_height), (220, 220, 220), 1)
        cv2.line(image, (margin_left, y), (margin_left + plot_width, y), (220, 220, 220), 1)

    if trace.shape[0] > 0:
        x_values = trace[:, 0]
        y_values = trace[:, 1]
        x_min = float(np.nanmin(x_values))
        x_max = float(np.nanmax(x_values))
        y_min = float(np.nanmin(y_values))
        y_max = float(np.nanmax(y_values))
        x_span = max(1e-9, x_max - x_min)
        y_span = max(1e-9, y_max - y_min)

        polyline = []
        for time_sec, value in trace:
            x = margin_left + int((time_sec - x_min) / x_span * plot_width)
            y = margin_top + plot_height - int((value - y_min) / y_span * plot_height)
            polyline.append([x, y])

        if len(polyline) > 1:
            cv2.polylines(
                image,
                [np.array(polyline, dtype=np.int32)],
                False,
                (20, 80, 200),
                1,
                lineType=cv2.LINE_AA,
            )

        cv2.putText(
            image,
            f"x: {x_min:.1f}..{x_max:.1f} sec",
            (margin_left, height - 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (40, 40, 40),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"y: {y_min:.1f}..{y_max:.1f}",
            (width - 260, height - 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (40, 40, 40),
            1,
            cv2.LINE_AA,
        )

    cv2.putText(
        image,
        title,
        (margin_left, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        y_label,
        (12, margin_top + 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (40, 40, 40),
        1,
        cv2.LINE_AA,
    )
    cv2.imwrite(path, image)


def _format_float(value):
    if np.isnan(value):
        return "NaN"
    if abs(value) < 0.5e-6:
        return "0.000000"
    return f"{float(value):.6f}"


def main():
    x0, seconds_per_pixel = compute_seconds_per_pixel(TIME_MARKS)

    upper_points = load_trace_csv(UPPER_POINTS_PATH)
    lower_points = load_trace_csv(LOWER_POINTS_PATH)

    fhr_trace = calibrate_trace(upper_points, x0, seconds_per_pixel, pixel_to_fhr)
    ua_trace = calibrate_trace(lower_points, x0, seconds_per_pixel, pixel_to_ua_kpa)
    merged_rows = merge_timeseries(fhr_trace, ua_trace)

    save_final_csv(RESULT_CSV_PATH, merged_rows)
    save_debug_plot(FHR_PLOT_PATH, fhr_trace, "fhr_bpm", "Calibrated FHR")
    save_debug_plot(UA_PLOT_PATH, ua_trace, "ua_kpa", "Calibrated UA")

    print("[INFO] Calibration module created")
    print("[INFO] Calibrated CSV generated")
    print("[INFO] Physical time series built")


if __name__ == "__main__":
    main()
