import csv
import os

import cv2
import numpy as np

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ModuleNotFoundError:
    HAS_MATPLOTLIB = False


RESULTS_DIR = os.path.join("results", "python")
DEBUG_DIR = os.path.join(RESULTS_DIR, "debug")

ALIGNED_PATH = os.path.join(RESULTS_DIR, "aligned.png")
UPPER_PANEL_PATH = os.path.join(RESULTS_DIR, "upper_panel.png")
LOWER_PANEL_PATH = os.path.join(RESULTS_DIR, "lower_panel.png")
UPPER_POINTS_PATH = os.path.join(DEBUG_DIR, "upper_points.csv")
LOWER_POINTS_PATH = os.path.join(DEBUG_DIR, "lower_points.csv")

RESULT_CSV_PATH = os.path.join(RESULTS_DIR, "result.csv")
RESULT_SPARSE_CSV_PATH = os.path.join(RESULTS_DIR, "result_sparse.csv")
FHR_TIMESERIES_PATH = os.path.join(RESULTS_DIR, "fhr_timeseries.csv")
UA_TIMESERIES_PATH = os.path.join(RESULTS_DIR, "ua_timeseries.csv")
CALIBRATION_PARAMS_PATH = os.path.join(RESULTS_DIR, "calibration_params.txt")

FHR_PLOT_PATH = os.path.join(DEBUG_DIR, "calibrated_fhr_plot.png")
UA_PLOT_PATH = os.path.join(DEBUG_DIR, "calibrated_ua_plot.png")
UPPER_CALIBRATION_MARKS_PATH = os.path.join(DEBUG_DIR, "upper_calibration_marks.png")
LOWER_CALIBRATION_MARKS_PATH = os.path.join(DEBUG_DIR, "lower_calibration_marks.png")
TIME_CALIBRATION_MARKS_PATH = os.path.join(DEBUG_DIR, "time_calibration_marks.png")

# Калибровочные точки задаются вручную по debug-изображениям upper_panel.png и lower_panel.png.
# Временные метки задаются по aligned.png.
TIME_MARKS = [
    (216.0, "09:04:38"),
    (795.0, "09:08:38"),
    (1374.0, "09:12:38"),
    (1953.0, "09:16:38"),
]

# Опоры шкалы FHR: горизонтальные линии 200 и 60 bpm на верхней панели.
FHR_TOP_Y = 70.0
FHR_BOTTOM_Y = 1040.0
FHR_TOP_VALUE = 200.0
FHR_BOTTOM_VALUE = 60.0

# Опоры шкалы UA: горизонтальные линии 12 и 0 kPa на нижней панели.
UA_TOP_Y = 127.0
UA_BOTTOM_Y = 657.0
UA_TOP_KPA = 12.0
UA_BOTTOM_KPA = 0.0

KPA_TO_MMHG = 7.50062
OUTPUT_DT_SEC = 1.0
MAX_INTERP_GAP_SEC_FHR = 15.0
MAX_INTERP_GAP_SEC_UA = 20.0


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


def merge_timeseries_sparse(fhr_trace, ua_trace):
    """Старое точное объединение FHR и UA без ресемплинга."""
    rows_by_time = {}

    for time_sec, fhr_bpm in fhr_trace:
        time_key = round(float(time_sec), 6)
        rows_by_time.setdefault(time_key, _empty_result_row(float(time_sec)))
        rows_by_time[time_key]["fhr_bpm"] = float(fhr_bpm)

    for time_sec, ua_kpa in ua_trace:
        time_key = round(float(time_sec), 6)
        rows_by_time.setdefault(time_key, _empty_result_row(float(time_sec)))
        rows_by_time[time_key]["ua_kpa"] = float(ua_kpa)
        rows_by_time[time_key]["ua_mmhg"] = float(pixel_to_ua_mmhg(ua_kpa))

    return _rows_from_time_map(rows_by_time)


def merge_timeseries(
    fhr_trace,
    ua_trace,
    output_dt_sec=OUTPUT_DT_SEC,
    max_gap_sec_fhr=MAX_INTERP_GAP_SEC_FHR,
    max_gap_sec_ua=MAX_INTERP_GAP_SEC_UA,
):
    """Объединяет FHR и UA на общей регулярной временной сетке."""
    max_time = max(_max_time(fhr_trace), _max_time(ua_trace))
    if max_time <= 0:
        return []

    end_time = np.floor(max_time / output_dt_sec) * output_dt_sec
    time_grid = np.arange(0.0, end_time + output_dt_sec * 0.5, output_dt_sec)
    fhr_values = interpolate_trace_to_grid(fhr_trace, time_grid, max_gap_sec_fhr)
    ua_kpa_values = interpolate_trace_to_grid(ua_trace, time_grid, max_gap_sec_ua)
    ua_mmhg_values = pixel_to_ua_mmhg(ua_kpa_values)

    rows = []
    for sample_idx, time_sec in enumerate(time_grid):
        rows.append(
            {
                "sample_idx": sample_idx,
                "time_sec": float(time_sec),
                "fhr_bpm": float(fhr_values[sample_idx]),
                "ua_kpa": float(ua_kpa_values[sample_idx]),
                "ua_mmhg": float(ua_mmhg_values[sample_idx]),
            }
        )

    return rows


def interpolate_trace_to_grid(trace, time_grid, max_gap_sec):
    """Линейно интерполирует ряд, не заполняя слишком большие разрывы."""
    if trace.shape[0] == 0 or time_grid.shape[0] == 0:
        return np.full(time_grid.shape[0], np.nan, dtype=np.float64)

    times, values = _sorted_unique_trace(trace)
    result = np.full(time_grid.shape[0], np.nan, dtype=np.float64)
    left_indices = np.searchsorted(times, time_grid, side="right") - 1
    right_indices = np.searchsorted(times, time_grid, side="left")
    inside = (left_indices >= 0) & (right_indices < times.shape[0])

    if not np.any(inside):
        return result

    left_distance = time_grid[inside] - times[left_indices[inside]]
    right_distance = times[right_indices[inside]] - time_grid[inside]
    gap_ok = (left_distance <= max_gap_sec) & (right_distance <= max_gap_sec)
    valid_indices = np.where(inside)[0][gap_ok]

    if valid_indices.shape[0] > 0:
        interpolated = np.interp(time_grid[valid_indices], times, values)
        result[valid_indices] = interpolated

    return result


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


def save_fhr_timeseries_csv(path, fhr_trace):
    """Сохраняет отдельный откалиброванный FHR-ряд."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["sample_idx", "time_sec", "fhr_bpm"])
        writer.writeheader()
        for sample_idx, (time_sec, fhr_bpm) in enumerate(fhr_trace):
            writer.writerow(
                {
                    "sample_idx": sample_idx,
                    "time_sec": _format_float(time_sec),
                    "fhr_bpm": _format_float(fhr_bpm),
                }
            )


def save_ua_timeseries_csv(path, ua_trace):
    """Сохраняет отдельный откалиброванный UA-ряд."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["sample_idx", "time_sec", "ua_kpa", "ua_mmhg"],
        )
        writer.writeheader()
        for sample_idx, (time_sec, ua_kpa) in enumerate(ua_trace):
            writer.writerow(
                {
                    "sample_idx": sample_idx,
                    "time_sec": _format_float(time_sec),
                    "ua_kpa": _format_float(ua_kpa),
                    "ua_mmhg": _format_float(pixel_to_ua_mmhg(ua_kpa)),
                }
            )


def save_calibration_mark_images():
    """Сохраняет изображения с ручными калибровочными опорами."""
    upper_image = _load_image(UPPER_PANEL_PATH)
    lower_image = _load_image(LOWER_PANEL_PATH)
    aligned_image = _load_image(ALIGNED_PATH)

    _draw_horizontal_mark(upper_image, FHR_TOP_Y, "200 bpm", (40, 80, 240))
    _draw_horizontal_mark(upper_image, FHR_BOTTOM_Y, "60 bpm", (40, 160, 240))
    cv2.imwrite(UPPER_CALIBRATION_MARKS_PATH, upper_image)

    _draw_horizontal_mark(lower_image, UA_TOP_Y, "12 kPa", (40, 80, 240))
    _draw_horizontal_mark(lower_image, UA_BOTTOM_Y, "0 kPa", (40, 160, 240))
    cv2.imwrite(LOWER_CALIBRATION_MARKS_PATH, lower_image)

    for index, (x_px, time_label) in enumerate(TIME_MARKS):
        _draw_vertical_mark(aligned_image, x_px, time_label, index)
    cv2.imwrite(TIME_CALIBRATION_MARKS_PATH, aligned_image)


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


def print_diagnostics(x0, seconds_per_pixel, fhr_trace, ua_trace, result_rows):
    """Печатает диагностику качества калибровки."""
    fhr_values = fhr_trace[:, 1] if fhr_trace.shape[0] > 0 else np.array([], dtype=np.float64)
    ua_kpa_values = ua_trace[:, 1] if ua_trace.shape[0] > 0 else np.array([], dtype=np.float64)
    ua_mmhg_values = pixel_to_ua_mmhg(ua_kpa_values)
    result_duration = result_rows[-1]["time_sec"] - result_rows[0]["time_sec"] if result_rows else 0.0

    print(f"[INFO] x0: {x0:.3f} px")
    print(f"[INFO] seconds_per_pixel: {seconds_per_pixel:.6f}")
    print(f"[INFO] result duration: {result_duration:.2f} sec ({result_duration / 60.0:.2f} min)")
    print(f"[INFO] fhr_bpm min/max: {_format_range(fhr_values)}")
    print(f"[INFO] ua_kpa min/max: {_format_range(ua_kpa_values)}")
    print(f"[INFO] ua_mmhg min/max: {_format_range(ua_mmhg_values)}")
    print(f"[INFO] result rows: {len(result_rows)}")
    print(f"[INFO] NaN fhr_bpm: {_count_nan_rows(result_rows, 'fhr_bpm')}")
    print(f"[INFO] NaN ua_kpa: {_count_nan_rows(result_rows, 'ua_kpa')}")
    print(f"[INFO] NaN ua_mmhg: {_count_nan_rows(result_rows, 'ua_mmhg')}")

    _warn_if_range_outside("fhr_bpm", fhr_values, 50.0, 210.0)
    _warn_if_range_outside("ua_kpa", ua_kpa_values, -0.5, 13.0)
    _warn_if_many_negative_times(fhr_trace, ua_trace)


def save_calibration_params(path, x0, seconds_per_pixel, fhr_trace, ua_trace, result_rows):
    """Сохраняет финальные параметры ручной калибровки."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    fhr_values = fhr_trace[:, 1] if fhr_trace.shape[0] > 0 else np.array([], dtype=np.float64)
    ua_kpa_values = ua_trace[:, 1] if ua_trace.shape[0] > 0 else np.array([], dtype=np.float64)
    ua_mmhg_values = pixel_to_ua_mmhg(ua_kpa_values)
    result_duration = result_rows[-1]["time_sec"] - result_rows[0]["time_sec"] if result_rows else 0.0

    with open(path, "w", encoding="utf-8") as params_file:
        params_file.write("Calibration parameters\n")
        params_file.write("======================\n\n")
        params_file.write("TIME_MARKS:\n")
        for x_px, time_label in TIME_MARKS:
            params_file.write(f"  {x_px:.3f}, {time_label}\n")
        params_file.write("\n")
        params_file.write(f"x0_px: {x0:.6f}\n")
        params_file.write(f"seconds_per_pixel: {seconds_per_pixel:.9f}\n")
        params_file.write(f"OUTPUT_DT_SEC: {OUTPUT_DT_SEC:.6f}\n")
        params_file.write(f"MAX_INTERP_GAP_SEC_FHR: {MAX_INTERP_GAP_SEC_FHR:.6f}\n")
        params_file.write(f"MAX_INTERP_GAP_SEC_UA: {MAX_INTERP_GAP_SEC_UA:.6f}\n\n")
        params_file.write(f"FHR_TOP_Y: {FHR_TOP_Y:.3f}\n")
        params_file.write(f"FHR_BOTTOM_Y: {FHR_BOTTOM_Y:.3f}\n")
        params_file.write(f"FHR_TOP_VALUE: {FHR_TOP_VALUE:.3f}\n")
        params_file.write(f"FHR_BOTTOM_VALUE: {FHR_BOTTOM_VALUE:.3f}\n\n")
        params_file.write(f"UA_TOP_Y: {UA_TOP_Y:.3f}\n")
        params_file.write(f"UA_BOTTOM_Y: {UA_BOTTOM_Y:.3f}\n")
        params_file.write(f"UA_TOP_KPA: {UA_TOP_KPA:.3f}\n")
        params_file.write(f"UA_BOTTOM_KPA: {UA_BOTTOM_KPA:.3f}\n")
        params_file.write(f"KPA_TO_MMHG: {KPA_TO_MMHG:.6f}\n\n")
        params_file.write("Output ranges:\n")
        params_file.write(f"  result_duration_sec: {result_duration:.6f}\n")
        params_file.write(f"  result_duration_min: {result_duration / 60.0:.6f}\n")
        params_file.write(f"  result_rows: {len(result_rows)}\n")
        params_file.write(f"  fhr_bpm: {_format_range(fhr_values)}\n")
        params_file.write(f"  ua_kpa: {_format_range(ua_kpa_values)}\n")
        params_file.write(f"  ua_mmhg: {_format_range(ua_mmhg_values)}\n")
        params_file.write(f"  NaN fhr_bpm: {_count_nan_rows(result_rows, 'fhr_bpm')}\n")
        params_file.write(f"  NaN ua_kpa: {_count_nan_rows(result_rows, 'ua_kpa')}\n")
        params_file.write(f"  NaN ua_mmhg: {_count_nan_rows(result_rows, 'ua_mmhg')}\n")


def _empty_result_row(time_sec):
    return {
        "time_sec": time_sec,
        "fhr_bpm": np.nan,
        "ua_kpa": np.nan,
        "ua_mmhg": np.nan,
    }


def _rows_from_time_map(rows_by_time):
    rows = []
    for sample_idx, time_key in enumerate(sorted(rows_by_time)):
        row = rows_by_time[time_key]
        rows.append(
            {
                "sample_idx": sample_idx,
                "time_sec": row["time_sec"],
                "fhr_bpm": row["fhr_bpm"],
                "ua_kpa": row["ua_kpa"],
                "ua_mmhg": row["ua_mmhg"],
            }
        )
    return rows


def _sorted_unique_trace(trace):
    order = np.argsort(trace[:, 0])
    times = trace[order, 0]
    values = trace[order, 1]
    unique_times, inverse = np.unique(times, return_inverse=True)

    if unique_times.shape[0] == times.shape[0]:
        return times, values

    sums = np.zeros(unique_times.shape[0], dtype=np.float64)
    counts = np.zeros(unique_times.shape[0], dtype=np.float64)
    np.add.at(sums, inverse, values)
    np.add.at(counts, inverse, 1.0)
    return unique_times, sums / counts


def _max_time(trace):
    if trace.shape[0] == 0:
        return 0.0
    return float(np.nanmax(trace[:, 0]))


def _load_image(path):
    image = cv2.imread(path)
    if image is None:
        raise FileNotFoundError(path)
    return image


def _draw_horizontal_mark(image, y_px, label, color):
    y = int(round(y_px))
    y = max(0, min(image.shape[0] - 1, y))
    cv2.line(image, (0, y), (image.shape[1] - 1, y), color, 2, lineType=cv2.LINE_AA)
    _draw_label(image, 18, y - 10, label, color)


def _draw_vertical_mark(image, x_px, label, index):
    x = int(round(x_px))
    x = max(0, min(image.shape[1] - 1, x))
    y = 35 + index * 34
    cv2.line(image, (x, 0), (x, image.shape[0] - 1), (40, 80, 240), 2, lineType=cv2.LINE_AA)
    _draw_label(image, x + 8, y, label, (40, 80, 240))


def _draw_label(image, x, y, text, color):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.8
    thickness = 2
    x = max(0, min(image.shape[1] - 1, int(x)))
    y = max(26, min(image.shape[0] - 8, int(y)))
    (text_width, text_height), _ = cv2.getTextSize(text, font, scale, thickness)
    x = min(x, max(0, image.shape[1] - text_width - 12))
    cv2.rectangle(
        image,
        (x - 4, y - text_height - 8),
        (x + text_width + 8, y + 6),
        (255, 255, 255),
        -1,
    )
    cv2.putText(image, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def _format_float(value):
    if np.isnan(value):
        return "NaN"
    if abs(value) < 0.5e-6:
        return "0.000000"
    return f"{float(value):.6f}"


def _format_range(values):
    finite_values = values[np.isfinite(values)]
    if finite_values.shape[0] == 0:
        return "NaN..NaN"
    return f"{float(np.min(finite_values)):.3f}..{float(np.max(finite_values)):.3f}"


def _count_nan_rows(rows, field_name):
    return sum(1 for row in rows if np.isnan(row[field_name]))


def _warn_if_range_outside(name, values, min_allowed, max_allowed):
    finite_values = values[np.isfinite(values)]
    if finite_values.shape[0] == 0:
        print(f"[WARN] {name} has no finite values")
        return

    value_min = float(np.min(finite_values))
    value_max = float(np.max(finite_values))
    if value_min < min_allowed or value_max > max_allowed:
        print(
            f"[WARN] {name} outside expected range "
            f"{min_allowed:.1f}..{max_allowed:.1f}: {value_min:.3f}..{value_max:.3f}"
        )


def _warn_if_many_negative_times(fhr_trace, ua_trace):
    all_times = np.concatenate([fhr_trace[:, 0], ua_trace[:, 0]])
    negative_count = int(np.count_nonzero(all_times < -1e-6))
    warning_limit = max(10, int(all_times.shape[0] * 0.01))
    if negative_count > warning_limit:
        print(f"[WARN] Many negative time_sec values: {negative_count}/{all_times.shape[0]}")


def main():
    x0, seconds_per_pixel = compute_seconds_per_pixel(TIME_MARKS)

    upper_points = load_trace_csv(UPPER_POINTS_PATH)
    lower_points = load_trace_csv(LOWER_POINTS_PATH)

    fhr_trace = calibrate_trace(upper_points, x0, seconds_per_pixel, pixel_to_fhr)
    ua_trace = calibrate_trace(lower_points, x0, seconds_per_pixel, pixel_to_ua_kpa)
    sparse_rows = merge_timeseries_sparse(fhr_trace, ua_trace)
    result_rows = merge_timeseries(fhr_trace, ua_trace)

    save_fhr_timeseries_csv(FHR_TIMESERIES_PATH, fhr_trace)
    save_ua_timeseries_csv(UA_TIMESERIES_PATH, ua_trace)
    save_final_csv(RESULT_SPARSE_CSV_PATH, sparse_rows)
    save_final_csv(RESULT_CSV_PATH, result_rows)
    save_calibration_mark_images()
    save_debug_plot(FHR_PLOT_PATH, fhr_trace, "fhr_bpm", "Calibrated FHR")
    save_debug_plot(UA_PLOT_PATH, ua_trace, "ua_kpa", "Calibrated UA")
    print_diagnostics(x0, seconds_per_pixel, fhr_trace, ua_trace, result_rows)
    save_calibration_params(CALIBRATION_PARAMS_PATH, x0, seconds_per_pixel, fhr_trace, ua_trace, result_rows)
    print(f"[INFO] Calibration params saved: {CALIBRATION_PARAMS_PATH}")

    print("[INFO] Calibration module created")
    print("[INFO] Calibrated CSV generated")
    print("[INFO] Physical time series built")


if __name__ == "__main__":
    main()
