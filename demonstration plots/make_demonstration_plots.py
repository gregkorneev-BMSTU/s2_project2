from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ModuleNotFoundError:
    HAS_MATPLOTLIB = False


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RESULTS_DIR = PROJECT_ROOT / "results" / "python"
DEBUG_DIR = RESULTS_DIR / "debug"

UPPER_PANEL_PATH = RESULTS_DIR / "upper_panel.png"
LOWER_PANEL_PATH = RESULTS_DIR / "lower_panel.png"
UPPER_POINTS_PATH = DEBUG_DIR / "upper_points.csv"
LOWER_POINTS_PATH = DEBUG_DIR / "lower_points.csv"
FHR_TIMESERIES_PATH = RESULTS_DIR / "fhr_timeseries.csv"
UA_TIMESERIES_PATH = RESULTS_DIR / "ua_timeseries.csv"

UPPER_TRACE_PATH = SCRIPT_DIR / "upper_trace_from_coordinates.png"
LOWER_TRACE_PATH = SCRIPT_DIR / "lower_trace_from_coordinates.png"
UPPER_OVERLAY_PATH = SCRIPT_DIR / "upper_trace_overlay.png"
LOWER_OVERLAY_PATH = SCRIPT_DIR / "lower_trace_overlay.png"
CALIBRATED_TIMESERIES_PATH = SCRIPT_DIR / "calibrated_timeseries.png"
SUMMARY_PATH = SCRIPT_DIR / "demonstration_summary.png"

TRACE_COLOR = (20, 20, 20)
OVERLAY_COLOR = (20, 40, 230)
GRID_COLOR = (235, 215, 215)
MAX_CONNECTED_X_GAP_PX = 3


def main() -> None:
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    upper_panel = load_image(UPPER_PANEL_PATH)
    lower_panel = load_image(LOWER_PANEL_PATH)
    upper_points = load_points(UPPER_POINTS_PATH)
    lower_points = load_points(LOWER_POINTS_PATH)

    upper_trace = build_coordinate_trace_image(upper_panel.shape, upper_points)
    lower_trace = build_coordinate_trace_image(lower_panel.shape, lower_points)
    upper_overlay = build_overlay_image(upper_panel, upper_points)
    lower_overlay = build_overlay_image(lower_panel, lower_points)

    save_image(UPPER_TRACE_PATH, upper_trace)
    save_image(LOWER_TRACE_PATH, lower_trace)
    save_image(UPPER_OVERLAY_PATH, upper_overlay)
    save_image(LOWER_OVERLAY_PATH, lower_overlay)

    save_calibrated_timeseries_plot()
    save_summary_image(upper_trace, lower_trace, upper_overlay, lower_overlay)

    print(f"[INFO] Saved: {UPPER_TRACE_PATH.relative_to(PROJECT_ROOT)}")
    print(f"[INFO] Saved: {LOWER_TRACE_PATH.relative_to(PROJECT_ROOT)}")
    print(f"[INFO] Saved: {UPPER_OVERLAY_PATH.relative_to(PROJECT_ROOT)}")
    print(f"[INFO] Saved: {LOWER_OVERLAY_PATH.relative_to(PROJECT_ROOT)}")
    print(f"[INFO] Saved: {CALIBRATED_TIMESERIES_PATH.relative_to(PROJECT_ROOT)}")
    print(f"[INFO] Saved: {SUMMARY_PATH.relative_to(PROJECT_ROOT)}")


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Image not found: {path}")
    return image


def load_points(path: Path) -> np.ndarray:
    rows: list[tuple[int, int]] = []

    with path.open("r", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            rows.append((int(round(float(row["x_px"]))), int(round(float(row["y_px"])))))

    if not rows:
        return np.empty((0, 2), dtype=np.int32)

    return np.array(rows, dtype=np.int32)


def build_coordinate_trace_image(panel_shape: tuple[int, int, int], points: np.ndarray) -> np.ndarray:
    height, width = panel_shape[:2]
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    draw_soft_grid(canvas)
    draw_trace(canvas, points, TRACE_COLOR, thickness=2)
    return canvas


def build_overlay_image(panel: np.ndarray, points: np.ndarray) -> np.ndarray:
    overlay = panel.copy()
    trace_layer = np.zeros_like(panel)
    draw_trace(trace_layer, points, OVERLAY_COLOR, thickness=3)
    mask = np.any(trace_layer > 0, axis=2)
    overlay[mask] = cv2.addWeighted(panel[mask], 0.30, trace_layer[mask], 0.70, 0)
    return overlay


def draw_soft_grid(image: np.ndarray) -> None:
    height, width = image.shape[:2]

    for x in range(0, width, 40):
        color = GRID_COLOR if x % 200 else (220, 185, 185)
        cv2.line(image, (x, 0), (x, height - 1), color, 1)

    for y in range(0, height, 40):
        color = GRID_COLOR if y % 200 else (220, 185, 185)
        cv2.line(image, (0, y), (width - 1, y), color, 1)


def draw_trace(image: np.ndarray, points: np.ndarray, color: tuple[int, int, int], thickness: int) -> None:
    if points.shape[0] == 0:
        return

    height, width = image.shape[:2]
    clipped = points.copy()
    clipped[:, 0] = np.clip(clipped[:, 0], 0, width - 1)
    clipped[:, 1] = np.clip(clipped[:, 1], 0, height - 1)

    for segment in split_into_connected_segments(clipped):
        if segment.shape[0] == 1:
            x, y = segment[0]
            cv2.circle(image, (int(x), int(y)), max(1, thickness), color, -1, lineType=cv2.LINE_AA)
        else:
            cv2.polylines(
                image,
                [segment.reshape(-1, 1, 2)],
                isClosed=False,
                color=color,
                thickness=thickness,
                lineType=cv2.LINE_AA,
            )


def split_into_connected_segments(points: np.ndarray) -> list[np.ndarray]:
    if points.shape[0] <= 1:
        return [points]

    segments = []
    start = 0

    for index in range(1, points.shape[0]):
        x_gap = abs(int(points[index, 0]) - int(points[index - 1, 0]))
        if x_gap > MAX_CONNECTED_X_GAP_PX:
            segments.append(points[start:index])
            start = index

    segments.append(points[start:])
    return segments


def save_calibrated_timeseries_plot() -> None:
    fhr_rows = load_numeric_csv(FHR_TIMESERIES_PATH, ["time_sec", "fhr_bpm"])
    ua_rows = load_numeric_csv(UA_TIMESERIES_PATH, ["time_sec", "ua_kpa"])

    if HAS_MATPLOTLIB:
        save_calibrated_timeseries_plot_matplotlib(fhr_rows, ua_rows)
    else:
        save_calibrated_timeseries_plot_cv2(fhr_rows, ua_rows)


def load_numeric_csv(path: Path, fieldnames: list[str]) -> np.ndarray:
    rows = []

    with path.open("r", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            rows.append(tuple(float(row[field]) for field in fieldnames))

    if not rows:
        return np.empty((0, len(fieldnames)), dtype=np.float64)

    return np.array(rows, dtype=np.float64)


def save_calibrated_timeseries_plot_matplotlib(fhr_rows: np.ndarray, ua_rows: np.ndarray) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True)

    axes[0].plot(fhr_rows[:, 0] / 60.0, fhr_rows[:, 1], color="#111111", linewidth=1.1)
    axes[0].set_ylabel("FHR, bpm")
    axes[0].set_ylim(50, 210)
    axes[0].grid(True, color="#e8b9b9", linewidth=0.7, alpha=0.75)
    axes[0].grid(True, which="minor", color="#f2dada", linewidth=0.45, alpha=0.8)
    axes[0].minorticks_on()

    axes[1].plot(ua_rows[:, 0] / 60.0, ua_rows[:, 1], color="#111111", linewidth=1.1)
    axes[1].set_xlabel("time, min")
    axes[1].set_ylabel("UA, kPa")
    axes[1].set_ylim(-0.5, 13)
    axes[1].grid(True, color="#e8b9b9", linewidth=0.7, alpha=0.75)
    axes[1].grid(True, which="minor", color="#f2dada", linewidth=0.45, alpha=0.8)
    axes[1].minorticks_on()

    for axis in axes:
        axis.set_facecolor("#fffdfd")
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(CALIBRATED_TIMESERIES_PATH, dpi=160)
    plt.close(fig)


def save_calibrated_timeseries_plot_cv2(fhr_rows: np.ndarray, ua_rows: np.ndarray) -> None:
    width, height = 1600, 820
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    upper_rect = (90, 45, width - 40, 380)
    lower_rect = (90, 455, width - 40, height - 70)

    draw_series_cv2(canvas, fhr_rows, upper_rect, y_min=50, y_max=210, label="FHR, bpm")
    draw_series_cv2(canvas, ua_rows, lower_rect, y_min=-0.5, y_max=13, label="UA, kPa")
    cv2.putText(
        canvas,
        "time, min",
        (width // 2 - 45, height - 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (40, 40, 40),
        1,
        cv2.LINE_AA,
    )
    save_image(CALIBRATED_TIMESERIES_PATH, canvas)


def draw_series_cv2(
    canvas: np.ndarray,
    rows: np.ndarray,
    rect: tuple[int, int, int, int],
    y_min: float,
    y_max: float,
    label: str,
) -> None:
    x0, y0, x1, y1 = rect
    plot_width = x1 - x0
    plot_height = y1 - y0

    cv2.rectangle(canvas, (x0, y0), (x1, y1), (40, 40, 40), 1)

    for index in range(1, 10):
        x = x0 + int(plot_width * index / 10)
        cv2.line(canvas, (x, y0), (x, y1), GRID_COLOR, 1)

    for index in range(1, 8):
        y = y0 + int(plot_height * index / 8)
        cv2.line(canvas, (x0, y), (x1, y), GRID_COLOR, 1)

    if rows.shape[0] > 1:
        x_values = rows[:, 0] / 60.0
        y_values = rows[:, 1]
        x_min = float(np.nanmin(x_values))
        x_max = float(np.nanmax(x_values))
        x_span = max(1e-9, x_max - x_min)
        y_span = max(1e-9, y_max - y_min)
        polyline = []

        for x_value, y_value in zip(x_values, y_values):
            if not np.isfinite(y_value):
                continue
            x = x0 + int((x_value - x_min) / x_span * plot_width)
            y = y1 - int((y_value - y_min) / y_span * plot_height)
            polyline.append((x, y))

        if len(polyline) > 1:
            cv2.polylines(
                canvas,
                [np.array(polyline, dtype=np.int32).reshape(-1, 1, 2)],
                False,
                TRACE_COLOR,
                2,
                lineType=cv2.LINE_AA,
            )

    cv2.putText(
        canvas,
        label,
        (12, y0 + 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (40, 40, 40),
        1,
        cv2.LINE_AA,
    )


def save_summary_image(
    upper_trace: np.ndarray,
    lower_trace: np.ndarray,
    upper_overlay: np.ndarray,
    lower_overlay: np.ndarray,
) -> None:
    target_width = 1200
    margin = 24

    rows = [
        make_summary_row(
            "FHR / upper graph: coordinates over source",
            upper_overlay,
            "FHR / upper graph: coordinates only",
            upper_trace,
            target_width,
        ),
        make_summary_row(
            "UA / lower graph: coordinates over source",
            lower_overlay,
            "UA / lower graph: coordinates only",
            lower_trace,
            target_width,
        ),
    ]

    width = target_width * 2 + margin * 3
    height = sum(row.shape[0] for row in rows) + margin * (len(rows) + 1)
    summary = np.full((height, width, 3), 255, dtype=np.uint8)

    y = margin
    for row in rows:
        summary[y : y + row.shape[0], margin : margin + row.shape[1]] = row
        y += row.shape[0] + margin

    cv2.putText(
        summary,
        "Coordinate reconstruction check: two source graphs, two reconstructed traces",
        (margin, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (35, 35, 35),
        1,
        cv2.LINE_AA,
    )
    save_image(SUMMARY_PATH, summary)


def make_summary_row(
    left_label: str,
    left_image: np.ndarray,
    right_label: str,
    right_image: np.ndarray,
    target_width: int,
) -> np.ndarray:
    label_height = 34
    left = resize_to_width(left_image, target_width)
    right = resize_to_width(right_image, target_width)
    row_height = max(left.shape[0], right.shape[0]) + label_height
    row = np.full((row_height, target_width * 2 + 24, 3), 255, dtype=np.uint8)

    cv2.putText(row, left_label, (0, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (35, 35, 35), 1, cv2.LINE_AA)
    cv2.putText(
        row,
        right_label,
        (target_width + 24, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (35, 35, 35),
        1,
        cv2.LINE_AA,
    )

    row[label_height : label_height + left.shape[0], 0:target_width] = left
    row[label_height : label_height + right.shape[0], target_width + 24 : target_width * 2 + 24] = right
    return row


def resize_to_width(image: np.ndarray, target_width: int) -> np.ndarray:
    height, width = image.shape[:2]
    target_height = max(1, int(round(height * target_width / width)))
    return cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)


def save_image(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not save image: {path}")


if __name__ == "__main__":
    main()
