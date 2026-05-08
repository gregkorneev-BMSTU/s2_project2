import cv2
import numpy as np


MIN_COMPONENT_AREA = 80
MIN_COMPONENT_WIDTH = 2
MIN_COMPONENT_HEIGHT = 2
BORDER_CLEAN_WIDTH = 8
TRACE_GAP_LIMIT = 20
MAX_EDGE_ARTIFACT_WIDTH = 24
MIN_EDGE_ARTIFACT_HEIGHT_FRACTION = 0.45
MAX_TRACE_INTERPOLATION_GAP = 12
TOP_TEXT_ZONE_FRACTION = 0.12
MAX_TOP_TEXT_COMPONENT_AREA = 300
LOWER_SIGNAL_Y_END_FRACTION = 0.86
LOWER_LONG_COMPONENT_Y_FRACTION = 0.65
LOWER_LONG_COMPONENT_ASPECT_RATIO = 8.0
LOWER_LONG_COMPONENT_WIDTH_FRACTION = 0.15
LOWER_RIGHT_TEXT_X_FRACTION = 0.65
LOWER_RIGHT_TEXT_Y_FRACTION = 0.65
LOWER_RIGHT_TEXT_MAX_AREA = 1000
LOWER_RIGHT_TEXT_MAX_HEIGHT = 80
LOWER_RIGHT_TEXT_MAX_WIDTH = 300
LOWER_HORIZONTAL_KERNEL_WIDTH = 40
LOWER_HORIZONTAL_MIN_WIDTH = 100
LOWER_HORIZONTAL_MIN_ASPECT_RATIO = 8.0


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


def clean_signal_mask(mask, panel_type):
    """Очищает сырую маску сигнала от мелкого шума и краевых артефактов."""
    clean = mask.copy()
    mask_height, mask_width = clean.shape[:2]
    debug = {}
    removed_components_debug = np.zeros_like(clean)

    # Убираем черные полосы от границ фотографии, они мешают извлечению графика.
    clean[:, :BORDER_CLEAN_WIDTH] = 0
    clean[:, -BORDER_CLEAN_WIDTH:] = 0
    clean[:BORDER_CLEAN_WIDTH, :] = 0
    clean[-BORDER_CLEAN_WIDTH:, :] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    clean = cv2.morphologyEx(clean, cv2.MORPH_OPEN, kernel)
    debug["clean_before_roi_cut"] = clean.copy()

    if panel_type == "lower":
        roi_y_end = int(mask_height * LOWER_SIGNAL_Y_END_FRACTION)
        removed_components_debug[roi_y_end:, :] = clean[roi_y_end:, :]
        clean[roi_y_end:, :] = 0

    debug["clean_after_roi_cut"] = clean.copy()

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(clean, 8)
    filtered = np.zeros_like(clean)

    for component_id in range(1, component_count):
        x = stats[component_id, cv2.CC_STAT_LEFT]
        y = stats[component_id, cv2.CC_STAT_TOP]
        width = stats[component_id, cv2.CC_STAT_WIDTH]
        height = stats[component_id, cv2.CC_STAT_HEIGHT]
        area = stats[component_id, cv2.CC_STAT_AREA]

        if area < MIN_COMPONENT_AREA:
            continue
        if width < MIN_COMPONENT_WIDTH or height < MIN_COMPONENT_HEIGHT:
            continue
        if (
            x + width >= mask_width - 2
            and width <= MAX_EDGE_ARTIFACT_WIDTH
            and height >= mask_height * MIN_EDGE_ARTIFACT_HEIGHT_FRACTION
        ):
            continue
        if y <= mask_height * TOP_TEXT_ZONE_FRACTION and area <= MAX_TOP_TEXT_COMPONENT_AREA:
            continue
        if should_remove_lower_component(panel_type, mask_width, mask_height, x, y, width, height, area):
            removed_components_debug[labels == component_id] = 255
            continue

        filtered[labels == component_id] = 255

    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 3))
    filtered = cv2.morphologyEx(filtered, cv2.MORPH_CLOSE, close_kernel)
    filtered, removed_horizontal = remove_lower_horizontal_artifacts(filtered, panel_type)
    removed_components_debug = cv2.bitwise_or(removed_components_debug, removed_horizontal)
    filtered, removed_after_close = filter_signal_components(filtered, panel_type)
    removed_components_debug = cv2.bitwise_or(removed_components_debug, removed_after_close)
    debug["removed_components_debug"] = removed_components_debug

    return filtered, debug


def filter_signal_components(mask, panel_type):
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

        if area < MIN_COMPONENT_AREA:
            removed[labels == component_id] = 255
            continue
        if width < MIN_COMPONENT_WIDTH or height < MIN_COMPONENT_HEIGHT:
            removed[labels == component_id] = 255
            continue
        if (
            x + width >= mask_width - BORDER_CLEAN_WIDTH
            and width <= MAX_EDGE_ARTIFACT_WIDTH
            and height >= mask_height * MIN_EDGE_ARTIFACT_HEIGHT_FRACTION
        ):
            removed[labels == component_id] = 255
            continue
        if y <= mask_height * TOP_TEXT_ZONE_FRACTION and area <= MAX_TOP_TEXT_COMPONENT_AREA:
            removed[labels == component_id] = 255
            continue
        if should_remove_lower_component(panel_type, mask_width, mask_height, x, y, width, height, area):
            removed[labels == component_id] = 255
            continue

        filtered[labels == component_id] = 255

    return filtered, removed


def should_remove_lower_component(panel_type, mask_width, mask_height, x, y, width, height, area):
    """Проверяет нижние оси, подписи и служебные горизонтальные элементы."""
    if panel_type != "lower":
        return False

    aspect_ratio = width / max(1, height)
    is_lower_long_line = (
        y > mask_height * LOWER_LONG_COMPONENT_Y_FRACTION
        and aspect_ratio > LOWER_LONG_COMPONENT_ASPECT_RATIO
        and width > mask_width * LOWER_LONG_COMPONENT_WIDTH_FRACTION
    )
    is_right_lower_text = (
        x > mask_width * LOWER_RIGHT_TEXT_X_FRACTION
        and y > mask_height * LOWER_RIGHT_TEXT_Y_FRACTION
        and area < LOWER_RIGHT_TEXT_MAX_AREA
        and height < LOWER_RIGHT_TEXT_MAX_HEIGHT
        and width < LOWER_RIGHT_TEXT_MAX_WIDTH
    )

    return is_lower_long_line or is_right_lower_text


def remove_lower_horizontal_artifacts(mask, panel_type):
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

        if width >= LOWER_HORIZONTAL_MIN_WIDTH and aspect_ratio >= LOWER_HORIZONTAL_MIN_ASPECT_RATIO:
            removed[labels == component_id] = 255

    cleaned = mask.copy()
    cleaned[removed > 0] = 0

    return cleaned, removed


def extract_trace_points(mask):
    """Получает первичную линию графика: по одному y для каждого столбца с сигналом."""
    points = []
    previous_y = None

    for x in range(mask.shape[1]):
        ys = np.where(mask[:, x] > 0)[0]

        if len(ys) == 0:
            continue

        if previous_y is None:
            y = int(np.median(ys))
        else:
            closest_index = int(np.argmin(np.abs(ys - previous_y)))
            y = int(ys[closest_index])

        points.append((x, y))
        previous_y = y

    if len(points) < 2:
        return points

    filled_points = [points[0]]

    for point in points[1:]:
        previous_x, previous_y = filled_points[-1]
        x, y = point
        gap = x - previous_x

        if 1 < gap <= MAX_TRACE_INTERPOLATION_GAP:
            for offset in range(1, gap):
                ratio = offset / gap
                filled_y = int(round(previous_y + (y - previous_y) * ratio))
                filled_points.append((previous_x + offset, filled_y))

        filled_points.append(point)

    return filled_points


def make_overlay(panel_image, mask, trace_points=None, panel_type="upper"):
    """Накладывает маску и найденную линию на панель для отладки этапа 2."""
    overlay = panel_image.copy()

    green = np.zeros_like(overlay)
    green[:, :] = (0, 255, 0)
    overlay = np.where(mask[:, :, None] > 0, cv2.addWeighted(overlay, 0.35, green, 0.65, 0), overlay)

    if trace_points:
        previous = None

        for point in trace_points:
            if previous is not None and point[0] - previous[0] <= TRACE_GAP_LIMIT:
                cv2.line(overlay, previous, point, (0, 0, 255), 2)
            previous = point

    if panel_type == "lower":
        roi_y_end = int(panel_image.shape[0] * LOWER_SIGNAL_Y_END_FRACTION)
        cv2.line(overlay, (0, roi_y_end), (panel_image.shape[1] - 1, roi_y_end), (255, 0, 0), 2)

    return overlay


def analyze_panel(panel_image, panel_type):
    """Выполняет стартовую сегментацию одной панели."""
    raw_mask = extract_dark_mask(panel_image)
    clean_mask, debug = clean_signal_mask(raw_mask, panel_type)
    trace_points = extract_trace_points(clean_mask)
    overlay = make_overlay(panel_image, clean_mask, trace_points, panel_type)

    if panel_type == "lower":
        before_cleanup_points = extract_trace_points(debug["clean_before_roi_cut"])
        debug["trace_points_before_cleanup"] = len(before_cleanup_points)
        debug["trace_points_after_cleanup"] = len(trace_points)

    return raw_mask, clean_mask, trace_points, overlay, debug
