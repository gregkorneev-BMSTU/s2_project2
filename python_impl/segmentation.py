import cv2
import numpy as np


MIN_COMPONENT_AREA = 8
MIN_COMPONENT_WIDTH = 2
MIN_COMPONENT_HEIGHT = 2
BORDER_CLEAN_WIDTH = 8
TRACE_GAP_LIMIT_UPPER = 25
TRACE_GAP_LIMIT_LOWER = 50
MAX_EDGE_ARTIFACT_WIDTH = 24
MIN_EDGE_ARTIFACT_HEIGHT_FRACTION = 0.45
TOP_TEXT_ZONE_FRACTION = 0.12
MAX_TOP_TEXT_COMPONENT_AREA = 300
MAX_JUMP_UPPER = 80
MAX_JUMP_LOWER = 100
UPPER_MAX_INTERPOLATION_GAP = 20
LOWER_MAX_INTERPOLATION_GAP = 45
LOWER_SIGNAL_Y_END_FRACTION = 0.93
LOWER_SIGNAL_Y_END_FRACTION_STRICT = 0.86
LOWER_LONG_COMPONENT_Y_FRACTION = 0.70
LOWER_LONG_COMPONENT_ASPECT_RATIO = 12.0
LOWER_LONG_COMPONENT_WIDTH_FRACTION = 0.10
LOWER_LONG_COMPONENT_MAX_HEIGHT = 6
LOWER_RIGHT_TEXT_X_FRACTION = 0.60
LOWER_RIGHT_TEXT_Y_FRACTION = 0.55
LOWER_RIGHT_TEXT_MAX_AREA = 1200
LOWER_RIGHT_TEXT_MAX_HEIGHT = 90
LOWER_RIGHT_TEXT_MAX_WIDTH = 300
LOWER_HORIZONTAL_KERNEL_WIDTH = 40
LOWER_HORIZONTAL_MIN_WIDTH = 100
LOWER_HORIZONTAL_MIN_ASPECT_RATIO = 12.0
LOWER_HORIZONTAL_MAX_HEIGHT = 6
LOWER_BASELINE_KEEP_MIN_HEIGHT = 10
LOWER_BASELINE_KEEP_MIN_AREA = 30
LOWER_BASELINE_Y_FRACTION = 0.70


def split_panels(aligned_image):
    """Делит выровненное изображение на верхнюю и нижнюю панели."""
    height = aligned_image.shape[0]

    upper_start = int(height * 0.05)
    upper_end = int(height * 0.60)
    lower_start = int(height * 0.62)
    lower_end = int(height * 0.98)

    upper_panel = aligned_image[upper_start:upper_end, :].copy()
    lower_panel = aligned_image[lower_start:lower_end, :].copy()

    return upper_panel, lower_panel


def extract_dark_mask(panel_image):
    """Строит простую сырую маску темных пикселей для первичной проверки сигнала."""
    gray = cv2.cvtColor(panel_image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, raw_mask = cv2.threshold(blurred, 160, 255, cv2.THRESH_BINARY_INV)
    return raw_mask


def clean_signal_mask(mask, panel_type, cleanup_mode="soft"):
    """Очищает сырую маску сигнала от мелкого шума и краевых артефактов."""
    clean = mask.copy()
    mask_height, mask_width = clean.shape[:2]
    debug = {}

    # Убираем черные полосы от границ фотографии, они мешают извлечению графика.
    clean[:, :BORDER_CLEAN_WIDTH] = 0
    clean[:, -BORDER_CLEAN_WIDTH:] = 0
    clean[:BORDER_CLEAN_WIDTH, :] = 0
    clean[-BORDER_CLEAN_WIDTH:, :] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    clean = cv2.morphologyEx(clean, cv2.MORPH_OPEN, kernel)
    debug["clean_before_roi_cut"] = clean.copy()

    if panel_type == "lower":
        roi_fraction = get_lower_roi_fraction(cleanup_mode)
        roi_y_end = int(mask_height * roi_fraction)
        clean[roi_y_end:, :] = 0

    debug["clean_after_roi_cut"] = clean.copy()
    debug["mask_before_components"] = clean.copy()

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(clean, 8)
    filtered = np.zeros_like(clean)
    removed_components = np.zeros_like(clean)

    for component_id in range(1, component_count):
        x = stats[component_id, cv2.CC_STAT_LEFT]
        y = stats[component_id, cv2.CC_STAT_TOP]
        width = stats[component_id, cv2.CC_STAT_WIDTH]
        height = stats[component_id, cv2.CC_STAT_HEIGHT]
        area = stats[component_id, cv2.CC_STAT_AREA]

        if should_remove_component(
            panel_type,
            mask_width,
            mask_height,
            x,
            y,
            width,
            height,
            area,
            cleanup_mode,
        ):
            removed_components[labels == component_id] = 255
            continue
        filtered[labels == component_id] = 255

    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 3))
    filtered = cv2.morphologyEx(filtered, cv2.MORPH_CLOSE, close_kernel)
    filtered, removed_horizontal = remove_lower_horizontal_artifacts(filtered, panel_type, cleanup_mode)
    removed_components = cv2.bitwise_or(removed_components, removed_horizontal)
    filtered, removed_after_close = filter_signal_components(filtered, panel_type, cleanup_mode)
    removed_components = cv2.bitwise_or(removed_components, removed_after_close)
    debug["components_removed"] = removed_components
    debug["components_kept"] = filtered.copy()
    debug["removed_components_debug"] = removed_components
    debug["components_before_count"] = count_components(debug["mask_before_components"])
    debug["components_after_count"] = count_components(filtered)
    debug["components_removed_count"] = max(
        0,
        debug["components_before_count"] - debug["components_after_count"],
    )

    return filtered, debug


def filter_signal_components(mask, panel_type, cleanup_mode="soft"):
    """Удаляет мелкие компоненты и узкие высокие артефакты у правого края."""
    mask_height, mask_width = mask.shape[:2]
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    filtered = np.zeros_like(mask)
    removed = np.zeros_like(mask)

    for component_id in range(1, component_count):
        x = stats[component_id, cv2.CC_STAT_LEFT]
        y = stats[component_id, cv2.CC_STAT_TOP]
        width = stats[component_id, cv2.CC_STAT_WIDTH]
        height = stats[component_id, cv2.CC_STAT_HEIGHT]
        area = stats[component_id, cv2.CC_STAT_AREA]

        if should_remove_component(
            panel_type,
            mask_width,
            mask_height,
            x,
            y,
            width,
            height,
            area,
            cleanup_mode,
        ):
            removed[labels == component_id] = 255
            continue

        filtered[labels == component_id] = 255

    return filtered, removed


def should_remove_component(
    panel_type,
    mask_width,
    mask_height,
    x,
    y,
    width,
    height,
    area,
    cleanup_mode="soft",
):
    """Решает, удалять ли компоненту, не наказывая реальные вертикальные скачки."""
    aspect_ratio = width / max(1, height)

    if area < MIN_COMPONENT_AREA:
        return True
    if width < MIN_COMPONENT_WIDTH or height < MIN_COMPONENT_HEIGHT:
        return True
    if area < 40 and width < 10 and height < 10:
        return True
    if aspect_ratio > 15 and height < 5:
        return True
    if (
        x + width >= mask_width - BORDER_CLEAN_WIDTH
        and width <= MAX_EDGE_ARTIFACT_WIDTH
        and height >= mask_height * MIN_EDGE_ARTIFACT_HEIGHT_FRACTION
    ):
        return True

    if panel_type == "upper":
        return should_remove_upper_component(mask_height, y, area)

    return should_remove_lower_component(
        panel_type,
        mask_width,
        mask_height,
        x,
        y,
        width,
        height,
        area,
        cleanup_mode,
    )


def should_remove_upper_component(mask_height, y, area):
    """Удаляет верхние/нижние подписи верхней панели и короткий шум."""
    if area < 15:
        return True
    if y < mask_height * 0.08 and area < 800:
        return True
    if y > mask_height * 0.92 and area < 800:
        return True

    return False


def should_remove_lower_component(
    panel_type,
    mask_width,
    mask_height,
    x,
    y,
    width,
    height,
    area,
    cleanup_mode="soft",
):
    """Проверяет нижние оси, подписи и служебные горизонтальные элементы."""
    if panel_type != "lower":
        return False

    aspect_ratio = width / max(1, height)
    if area < 20:
        return True

    is_lower_long_line = (
        y > mask_height * LOWER_LONG_COMPONENT_Y_FRACTION
        and aspect_ratio > LOWER_LONG_COMPONENT_ASPECT_RATIO
        and height <= LOWER_LONG_COMPONENT_MAX_HEIGHT
        and width > mask_width * LOWER_LONG_COMPONENT_WIDTH_FRACTION
    )
    is_right_lower_text = (
        x > mask_width * LOWER_RIGHT_TEXT_X_FRACTION
        and y > mask_height * LOWER_RIGHT_TEXT_Y_FRACTION
        and area < LOWER_RIGHT_TEXT_MAX_AREA
        and height < LOWER_RIGHT_TEXT_MAX_HEIGHT
        and width < LOWER_RIGHT_TEXT_MAX_WIDTH
    )

    if is_lower_long_line or is_right_lower_text:
        return True

    is_low_signal_like = (
        y > mask_height * LOWER_BASELINE_Y_FRACTION
        and height >= LOWER_BASELINE_KEEP_MIN_HEIGHT
        and area >= LOWER_BASELINE_KEEP_MIN_AREA
    )
    if cleanup_mode == "soft" and is_low_signal_like:
        return False

    return False


def get_lower_roi_fraction(cleanup_mode):
    """Возвращает границу нижней панели для strict/soft сравнения."""
    if cleanup_mode == "strict":
        return LOWER_SIGNAL_Y_END_FRACTION_STRICT

    return LOWER_SIGNAL_Y_END_FRACTION


def count_components(mask):
    """Считает число связных компонент без фона."""
    component_count, _, _, _ = cv2.connectedComponentsWithStats(mask, 8)
    return max(0, component_count - 1)


def remove_lower_horizontal_artifacts(mask, panel_type, cleanup_mode="soft"):
    """Удаляет нижние почти горизонтальные служебные линии, даже если они склеены со скачком."""
    removed = np.zeros_like(mask)

    if panel_type != "lower":
        return mask, removed

    mask_height = mask.shape[0]
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (LOWER_HORIZONTAL_KERNEL_WIDTH, 3),
    )
    horizontal_mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, horizontal_kernel)
    horizontal_mask[: int(mask_height * LOWER_LONG_COMPONENT_Y_FRACTION), :] = 0

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(horizontal_mask, 8)

    for component_id in range(1, component_count):
        width = stats[component_id, cv2.CC_STAT_WIDTH]
        height = stats[component_id, cv2.CC_STAT_HEIGHT]
        aspect_ratio = width / max(1, height)

        if (
            width >= LOWER_HORIZONTAL_MIN_WIDTH
            and aspect_ratio >= LOWER_HORIZONTAL_MIN_ASPECT_RATIO
            and height <= LOWER_HORIZONTAL_MAX_HEIGHT
        ):
            removed[labels == component_id] = 255

    cleaned = mask.copy()
    cleaned[removed > 0] = 0

    return cleaned, removed


def extract_trace_points(mask, panel_type):
    """Получает первичную линию графика: по одному y для каждого столбца с сигналом."""
    points = []
    previous_y = None
    max_jump = MAX_JUMP_UPPER if panel_type == "upper" else MAX_JUMP_LOWER

    for x in range(mask.shape[1]):
        ys = np.where(mask[:, x] > 0)[0]

        if len(ys) == 0:
            previous_y = None
            continue

        if previous_y is None:
            y = int(np.median(ys))
        else:
            closest_index = int(np.argmin(np.abs(ys - previous_y)))
            y = int(ys[closest_index])

            is_lower_baseline_candidate = (
                panel_type == "lower"
                and y > mask.shape[0] * LOWER_BASELINE_Y_FRACTION
            )

            if abs(y - previous_y) > max_jump and not is_lower_baseline_candidate:
                previous_y = None
                continue

        points.append((x, y))
        previous_y = y

    return points


def interpolate_small_gaps(points, max_gap):
    """Заполняет короткие разрывы линейной интерполяцией."""
    if len(points) < 2:
        return points, set()

    filled_points = [points[0]]
    interpolated_points = set()

    for point in points[1:]:
        previous_x, previous_y = filled_points[-1]
        x, y = point
        gap = x - previous_x

        if 1 < gap <= max_gap:
            for offset in range(1, gap):
                ratio = offset / gap
                filled_y = int(round(previous_y + (y - previous_y) * ratio))
                filled_point = (previous_x + offset, filled_y)
                filled_points.append(filled_point)
                interpolated_points.add(filled_point)

        filled_points.append(point)

    return filled_points, interpolated_points


def count_large_gaps(points, gap_limit):
    """Считает разрывы по x, которые не надо соединять на overlay."""
    gap_count = 0

    for index in range(1, len(points)):
        if points[index][0] - points[index - 1][0] > gap_limit:
            gap_count += 1

    return gap_count


def make_overlay(
    panel_image,
    mask,
    trace_points=None,
    interpolated_points=None,
    panel_type="upper",
    cleanup_mode="soft",
):
    """Накладывает маску и найденную линию на панель для отладки этапа 2."""
    overlay = panel_image.copy()

    green = np.zeros_like(overlay)
    green[:, :] = (0, 255, 0)
    overlay = np.where(mask[:, :, None] > 0, cv2.addWeighted(overlay, 0.35, green, 0.65, 0), overlay)

    if trace_points:
        previous = None
        trace_gap_limit = TRACE_GAP_LIMIT_UPPER if panel_type == "upper" else TRACE_GAP_LIMIT_LOWER

        for point in trace_points:
            if previous is not None and point[0] - previous[0] <= trace_gap_limit:
                cv2.line(overlay, previous, point, (0, 0, 255), 2)
            previous = point

    if interpolated_points:
        for point in interpolated_points:
            cv2.circle(overlay, point, 2, (0, 255, 255), -1)

    if panel_type == "lower":
        roi_y_end = int(panel_image.shape[0] * get_lower_roi_fraction(cleanup_mode))
        cv2.line(overlay, (0, roi_y_end), (panel_image.shape[1] - 1, roi_y_end), (255, 0, 0), 2)

    return overlay


def make_trace_only(
    panel_shape,
    trace_points=None,
    interpolated_points=None,
    panel_type="upper",
    cleanup_mode="soft",
):
    """Создает отдельное изображение только с трассой и интерполяцией."""
    height, width = panel_shape[:2]
    trace_image = np.zeros((height, width, 3), dtype=np.uint8)

    if trace_points:
        previous = None
        trace_gap_limit = TRACE_GAP_LIMIT_UPPER if panel_type == "upper" else TRACE_GAP_LIMIT_LOWER

        for point in trace_points:
            if previous is not None and point[0] - previous[0] <= trace_gap_limit:
                cv2.line(trace_image, previous, point, (0, 0, 255), 2)
            previous = point

    if interpolated_points:
        for point in interpolated_points:
            cv2.circle(trace_image, point, 2, (0, 255, 255), -1)

    if panel_type == "lower":
        roi_y_end = int(height * get_lower_roi_fraction(cleanup_mode))
        cv2.line(trace_image, (0, roi_y_end), (width - 1, roi_y_end), (255, 0, 0), 2)

    return trace_image


def analyze_panel(panel_image, panel_type):
    """Выполняет стартовую сегментацию одной панели."""
    raw_mask = extract_dark_mask(panel_image)
    clean_mask, debug = analyze_clean_mask(panel_image, raw_mask, panel_type, "soft")

    if panel_type == "lower":
        strict_clean_mask, strict_debug = analyze_clean_mask(panel_image, raw_mask, panel_type, "strict")
        before_cleanup_points = extract_trace_points(strict_debug["clean_before_roi_cut"], panel_type)
        debug["strict_clean_mask"] = strict_clean_mask
        debug["strict_overlay"] = strict_debug["overlay"]
        debug["strict_debug"] = strict_debug
        debug["trace_points_before_cleanup"] = len(before_cleanup_points)
        debug["trace_points_after_cleanup"] = len(debug["interpolated_trace_points"])
        debug["selected_mode"] = "soft"

    return raw_mask, clean_mask, debug["interpolated_trace_points"], debug["overlay"], debug


def analyze_clean_mask(panel_image, raw_mask, panel_type, cleanup_mode):
    """Строит clean-маску и трассу для выбранного режима очистки."""
    clean_mask, debug = clean_signal_mask(raw_mask, panel_type, cleanup_mode)
    raw_trace_points = extract_trace_points(clean_mask, panel_type)
    max_gap = UPPER_MAX_INTERPOLATION_GAP if panel_type == "upper" else LOWER_MAX_INTERPOLATION_GAP
    trace_points, interpolated_points = interpolate_small_gaps(raw_trace_points, max_gap)
    overlay = make_overlay(
        panel_image,
        clean_mask,
        trace_points,
        interpolated_points,
        panel_type,
        cleanup_mode,
    )
    trace_only = make_trace_only(
        panel_image.shape,
        trace_points,
        interpolated_points,
        panel_type,
        cleanup_mode,
    )

    trace_gap_limit = TRACE_GAP_LIMIT_UPPER if panel_type == "upper" else TRACE_GAP_LIMIT_LOWER
    debug["raw_trace_points"] = raw_trace_points
    debug["interpolated_trace_points"] = trace_points
    debug["interpolated_points_set"] = interpolated_points
    debug["overlay"] = overlay
    debug["trace_only"] = trace_only
    debug["raw_points_count"] = len(raw_trace_points)
    debug["interpolated_points_count"] = len(trace_points)
    debug["large_gaps_count"] = count_large_gaps(raw_trace_points, trace_gap_limit)
    debug["trace_coverage"] = 100.0 * len(trace_points) / max(1, panel_image.shape[1])
    debug["cleanup_mode"] = cleanup_mode

    return clean_mask, debug
