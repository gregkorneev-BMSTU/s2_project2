import os

import numpy as np

from preprocess import (
    MIN_FILTERED_LINES_WARNING,
    create_debug_collage,
    ensure_dir,
    load_image,
    run_stage1_pipeline,
    save_image,
)
from segmentation import analyze_panel, split_panels


def find_input_path():
    """Ищет входной файл и сохраняет fallback на input.png."""
    jpg_path = os.path.join("data", "input.jpg")
    png_path = os.path.join("data", "input.png")

    if os.path.exists(jpg_path):
        return jpg_path

    if os.path.exists(png_path):
        print("[WARN] Файл data/input.jpg не найден, используется data/input.png")
        return png_path

    print("[WARN] Входной файл не найден: data/input.jpg")
    print("[WARN] Резервный файл data/input.png тоже не найден")
    return None


def print_mask_stats(mask_name, mask, reference_area):
    """Печатает число белых пикселей и их долю."""
    pixels = int(np.count_nonzero(mask))
    percent = 100.0 * pixels / max(1, reference_area)
    print(f"[INFO] {mask_name} pixels: {pixels} ({percent:.2f}%)")


def save_trace_points(path, trace_points):
    """Сохраняет пиксельный ряд графика в CSV."""
    if len(trace_points) == 0:
        points_array = np.empty((0, 2), dtype=np.int32)
    else:
        points_array = np.array(trace_points, dtype=np.int32)

    np.savetxt(
        path,
        points_array,
        fmt="%d",
        delimiter=",",
        header="x_px,y_px",
        comments="",
    )


def save_stage2_debug(debug_dir, panel_name, panel_debug):
    """Сохраняет промежуточные маски и трассы этапа 2."""
    save_image(
        os.path.join(debug_dir, f"{panel_name}_mask_before_components.png"),
        panel_debug["mask_before_components"],
    )
    save_image(
        os.path.join(debug_dir, f"{panel_name}_components_kept.png"),
        panel_debug["components_kept"],
    )
    save_image(
        os.path.join(debug_dir, f"{panel_name}_components_removed.png"),
        panel_debug["components_removed"],
    )
    save_image(os.path.join(debug_dir, f"{panel_name}_trace_only.png"), panel_debug["trace_only"])
    save_trace_points(
        os.path.join(debug_dir, f"{panel_name}_points_raw.csv"),
        panel_debug["raw_trace_points"],
    )
    save_trace_points(
        os.path.join(debug_dir, f"{panel_name}_points_interpolated.csv"),
        panel_debug["interpolated_trace_points"],
    )


def print_stage2_metrics(panel_title, panel_debug, panel_width):
    """Печатает метрики качества выделения сигнала."""
    title = panel_title.capitalize()

    print(f"[INFO] {title} components before: {panel_debug['components_before_count']}")
    print(f"[INFO] {title} components after: {panel_debug['components_after_count']}")
    print(f"[INFO] {title} components removed: {panel_debug['components_removed_count']}")
    print(f"[INFO] {title} raw points: {panel_debug['raw_points_count']}")
    print(f"[INFO] {title} interpolated points: {panel_debug['interpolated_points_count']}")
    print(f"[INFO] {title} large gaps: {panel_debug['large_gaps_count']}")
    print(f"[INFO] {title} trace coverage: {panel_debug['trace_coverage']:.2f}%")

    if panel_debug["trace_coverage"] < 50.0:
        print(f"[WARN] Низкое покрытие сигнала по ширине: {panel_title} ({panel_width}px)")


def save_stage1_outputs(results_python_dir, debug_dir, stage1_result):
    """Сохраняет все debug-артефакты этапа 1."""
    red_debug = stage1_result["red_debug"]
    line_debug = stage1_result["line_debug"]

    save_image(os.path.join(results_python_dir, "original.png"), stage1_result["original_image"])
    save_image(os.path.join(debug_dir, "red_mask_1.png"), red_debug["red_mask_1"])
    save_image(os.path.join(debug_dir, "red_mask_2.png"), red_debug["red_mask_2"])
    save_image(os.path.join(debug_dir, "red_like_mask.png"), red_debug["red_like_mask"])
    save_image(os.path.join(debug_dir, "lab_a_channel.png"), red_debug["lab_a_channel"])
    save_image(os.path.join(debug_dir, "red_from_lab_mask.png"), red_debug["red_from_lab_mask"])
    save_image(
        os.path.join(debug_dir, "red_mask_combined_before_morph.png"),
        red_debug["red_mask_combined_before_morph"],
    )
    save_image(
        os.path.join(debug_dir, "red_mask_after_close.png"),
        red_debug["red_mask_after_close"],
    )
    save_image(
        os.path.join(debug_dir, "red_mask_after_dilate.png"),
        red_debug["red_mask_after_dilate"],
    )
    save_image(os.path.join(debug_dir, "red_mask_clean.png"), stage1_result["red_mask_clean"])
    save_image(os.path.join(debug_dir, "red_mask.png"), stage1_result["red_mask_clean"])
    save_image(os.path.join(debug_dir, "search_roi_mask.png"), line_debug["search_roi_mask"])
    save_image(
        os.path.join(debug_dir, "horizontal_emphasis_mask.png"),
        line_debug["horizontal_emphasis_mask"],
    )
    save_image(os.path.join(debug_dir, "hough_input_mask.png"), line_debug["hough_input_mask"])
    save_image(os.path.join(debug_dir, "edges.png"), line_debug["edges"])
    save_image(os.path.join(debug_dir, "hough_lines_all.png"), stage1_result["hough_lines_all"])
    save_image(
        os.path.join(debug_dir, "hough_lines_filtered.png"),
        stage1_result["hough_lines_filtered"],
    )
    save_image(os.path.join(results_python_dir, "aligned.png"), stage1_result["aligned_image"])
    diff_image = np.abs(
        stage1_result["original_image"].astype(np.int16)
        - stage1_result["aligned_image"].astype(np.int16)
    )
    diff_image = np.clip(diff_image * 8, 0, 255).astype(np.uint8)
    save_image(os.path.join(debug_dir, "original_vs_aligned_diff.png"), diff_image)


def main():
    """Запускает этап выравнивания изображения."""
    input_path = find_input_path()
    if input_path is None:
        return

    results_dir = "results"
    results_python_dir = os.path.join(results_dir, "python")
    debug_dir = os.path.join(results_python_dir, "debug")

    ensure_dir(results_dir)
    ensure_dir(results_python_dir)
    ensure_dir(debug_dir)

    image = load_image(input_path)
    if image is None:
        print(f"[WARN] Не удалось загрузить изображение: {input_path}")
        return

    height, width = image.shape[:2]
    image_area = width * height
    print(f"[INFO] Размер изображения: {width}x{height}")

    stage1_result = run_stage1_pipeline(image)
    red_debug = stage1_result["red_debug"]
    line_debug = stage1_result["line_debug"]
    red_mask_clean = stage1_result["red_mask_clean"]
    all_lines = stage1_result["all_lines"]
    filtered_lines = stage1_result["filtered_lines"]
    angle = stage1_result["final_angle"]

    save_stage1_outputs(results_python_dir, debug_dir, stage1_result)

    print_mask_stats("red_mask_1", red_debug["red_mask_1"], image_area)
    print_mask_stats("red_mask_2", red_debug["red_mask_2"], image_area)
    print_mask_stats("red_like_mask", red_debug["red_like_mask"], image_area)
    print_mask_stats("lab_red_mask", red_debug["red_from_lab_mask"], image_area)
    print_mask_stats("red_mask", red_debug["red_mask_combined_before_morph"], image_area)
    print_mask_stats("cleaned red mask", red_mask_clean, image_area)

    roi_height = line_debug["roi_y_end"] - line_debug["roi_y_start"]
    roi_area = width * roi_height

    print(
        f"[INFO] Search ROI: y={line_debug['roi_y_start']}:{line_debug['roi_y_end']} "
        f"({width}x{roi_height})"
    )
    print_mask_stats("search_roi_mask", line_debug["search_roi_mask"], roi_area)
    print_mask_stats("horizontal emphasis mask", line_debug["horizontal_emphasis_mask"], roi_area)
    print_mask_stats("edges", line_debug["edges"], roi_area)
    print(f"[INFO] Hough mode: {line_debug['hough_mode']}")
    print(f"[INFO] Hough input used: {line_debug['hough_input_name']}")

    if line_debug["hough_mode"] == "mask":
        print(f"[INFO] Hough raw lines: {line_debug['mask_raw_lines']}")
        print(f"[INFO] Hough filtered horizontal lines: {line_debug['mask_filtered_lines']}")
    else:
        print(f"[INFO] Hough raw lines: {line_debug['edge_raw_lines']}")
        print(f"[INFO] Hough filtered horizontal lines: {line_debug['edge_filtered_lines']}")

    print(f"[INFO] Число найденных линий: {len(all_lines)}")
    print(f"[INFO] Число отфильтрованных линий: {len(filtered_lines)}")

    if len(all_lines) == 0:
        print("[WARN] Линии не найдены, используется угол 0 градусов")

    if 0 < len(filtered_lines) < MIN_FILTERED_LINES_WARNING:
        print("[WARN] Найдено мало горизонтальных линий, угол может быть неточным")

    if len(filtered_lines) == 0:
        print("[WARN] Горизонтальные линии не найдены, используется угол 0 градусов")
        angle = 0.0

    print(f"[INFO] Итоговый угол: {angle:.2f} градусов")

    debug_collage = create_debug_collage(
        [
            ("original", image),
            ("red_mask_1", red_debug["red_mask_1"]),
            ("red_mask_2", red_debug["red_mask_2"]),
            ("red_like_mask", red_debug["red_like_mask"]),
            ("red_from_lab", red_debug["red_from_lab_mask"]),
            ("red_mask_clean", red_mask_clean),
            ("horizontal_mask", line_debug["horizontal_emphasis_mask"]),
            ("hough_all", stage1_result["hough_lines_all"]),
            ("hough_filtered", stage1_result["hough_lines_filtered"]),
        ]
    )
    save_image(os.path.join(debug_dir, "debug_collage.png"), debug_collage)

    aligned_image = stage1_result["aligned_image"]
    upper_panel, lower_panel = split_panels(aligned_image)
    (
        upper_raw_mask,
        upper_clean_mask,
        upper_trace_points,
        upper_overlay,
        upper_debug,
    ) = analyze_panel(
        upper_panel,
        "upper",
    )
    (
        lower_raw_mask,
        lower_clean_mask,
        lower_trace_points,
        lower_overlay,
        lower_debug,
    ) = analyze_panel(lower_panel, "lower")

    save_image(os.path.join(results_python_dir, "upper_panel.png"), upper_panel)
    save_image(os.path.join(results_python_dir, "lower_panel.png"), lower_panel)
    save_image(os.path.join(debug_dir, "upper_raw_mask.png"), upper_raw_mask)
    save_image(os.path.join(debug_dir, "lower_raw_mask.png"), lower_raw_mask)
    save_image(os.path.join(debug_dir, "upper_clean_mask.png"), upper_clean_mask)
    save_image(os.path.join(debug_dir, "lower_clean_mask.png"), lower_clean_mask)
    save_image(os.path.join(debug_dir, "upper_signal_overlay.png"), upper_overlay)
    save_image(os.path.join(debug_dir, "lower_signal_overlay.png"), lower_overlay)
    save_stage2_debug(debug_dir, "upper", upper_debug)
    save_stage2_debug(debug_dir, "lower", lower_debug)
    save_image(
        os.path.join(debug_dir, "lower_clean_before_roi_cut.png"),
        lower_debug["clean_before_roi_cut"],
    )
    save_image(
        os.path.join(debug_dir, "lower_clean_after_roi_cut.png"),
        lower_debug["clean_after_roi_cut"],
    )
    save_image(
        os.path.join(debug_dir, "lower_removed_components_debug.png"),
        lower_debug["removed_components_debug"],
    )
    save_trace_points(os.path.join(debug_dir, "upper_points.csv"), upper_trace_points)
    save_trace_points(os.path.join(debug_dir, "lower_points.csv"), lower_trace_points)

    upper_height, upper_width = upper_panel.shape[:2]
    lower_height, lower_width = lower_panel.shape[:2]
    print(f"[INFO] upper_panel size: {upper_width}x{upper_height}")
    print(f"[INFO] lower_panel size: {lower_width}x{lower_height}")
    print_mask_stats("upper_raw_mask", upper_raw_mask, upper_width * upper_height)
    print_mask_stats("lower_raw_mask", lower_raw_mask, lower_width * lower_height)
    print_mask_stats("upper_clean_mask", upper_clean_mask, upper_width * upper_height)
    print_mask_stats("lower_clean_mask", lower_clean_mask, lower_width * lower_height)
    print_stage2_metrics("upper", upper_debug, upper_width)
    print_stage2_metrics("lower", lower_debug, lower_width)
    print(f"[INFO] upper_trace_points: {len(upper_trace_points)}")
    print(f"[INFO] lower trace points before cleanup: {lower_debug['trace_points_before_cleanup']}")
    print(f"[INFO] lower trace points after cleanup: {lower_debug['trace_points_after_cleanup']}")
    print(f"[INFO] lower_trace_points: {len(lower_trace_points)}")

    print("[INFO] Изображение выровнено")
    print(f"[INFO] Угол поворота: {angle:.2f} градусов")
    print("[INFO] Файлы сохранены в results/python/")
    print("[INFO] Debug-файлы сохранены в results/python/debug/")
    print("[INFO] Этап 1 повторно откалиброван под бледную красную сетку")
    print("[INFO] Проверь red_mask_clean.png, horizontal_emphasis_mask.png и hough_lines_filtered.png")
    print("[INFO] Этап 1 завершён успешно")
    print("[INFO] Можно переходить к этапу 2")
    print("[INFO] Этап 1 завершён успешно, можно переходить к этапу 2")
    print("[INFO] Созданы upper_panel/lower_panel и raw-маски для первичной проверки сигнала")
    print("[INFO] Этап 2: созданы clean-маски и overlay для первичной проверки линий графиков")
    print("[INFO] Этап 2 улучшен: маски очищены, трассировка обновлена")
    print("[INFO] Проверь upper_signal_overlay.png и lower_signal_overlay.png")


if __name__ == "__main__":
    main()
