import os

import cv2
import numpy as np


# Диапазоны HSV подобраны под бледную красную сетку на почти белом фоне.
# Насыщенность снижена, потому что сетка слабая и малонасыщенная.
LOWER_RED_1 = np.array([0, 10, 120], dtype=np.uint8)
UPPER_RED_1 = np.array([20, 255, 255], dtype=np.uint8)
LOWER_RED_2 = np.array([160, 10, 120], dtype=np.uint8)
UPPER_RED_2 = np.array([180, 255, 255], dtype=np.uint8)

# Дополнительная эвристика по разности каналов.
DELTA_RG = 8
DELTA_RB = 8

# Порог по нормализованному каналу a из LAB.
A_THRESHOLD = 140
USE_LAB_RED_MASK = True

# Параметры морфологии для усиления тонкой сетки.
MORPH_SIZE = 3
DILATE_ITERATIONS = 2
OPEN_ITERATIONS = 1
HORIZONTAL_KERNEL_WIDTH = 25

# Параметры ROI поиска сетки.
SEARCH_Y_START = 0.08
SEARCH_Y_END = 0.95

# Параметры Canny и Hough.
CANNY_LOW = 50
CANNY_HIGH = 150
HOUGH_THRESHOLD = 35
HOUGH_MIN_LINE_FRAC = 0.15
HOUGH_MAX_LINE_GAP = 40

# Параметры фильтрации почти горизонтальных линий.
ANGLE_THRESHOLD = 10.0
MIN_FILTERED_LINES_WARNING = 5


def ensure_dir(path):
    """Создает директорию, если она отсутствует."""
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def save_image(image_path, image):
    """Сохраняет изображение в файл."""
    ensure_dir(os.path.dirname(image_path))
    cv2.imwrite(image_path, image)


def load_image(image_path):
    """Загружает изображение с диска."""
    return cv2.imread(image_path)


def normalize_angle(angle_deg):
    """Приводит угол к диапазону около горизонтали."""
    if angle_deg > 90:
        angle_deg -= 180
    if angle_deg < -90:
        angle_deg += 180
    return angle_deg


def build_red_like_mask(image):
    """Строит маску красноватых пикселей по разности каналов."""
    blue, green, red = cv2.split(image)

    red_int = red.astype(np.int16)
    green_int = green.astype(np.int16)
    blue_int = blue.astype(np.int16)

    red_like = (red_int > green_int + DELTA_RG) & (red_int > blue_int + DELTA_RB)
    return (red_like.astype(np.uint8)) * 255


def build_lab_red_mask(image):
    """Строит дополнительную маску красноты по каналу a в LAB."""
    lab_image = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    a_channel = lab_image[:, :, 1]
    lab_a_channel = cv2.normalize(a_channel, None, 0, 255, cv2.NORM_MINMAX)

    _, red_from_lab_mask = cv2.threshold(
        lab_a_channel,
        A_THRESHOLD,
        255,
        cv2.THRESH_BINARY,
    )

    return lab_a_channel, red_from_lab_mask


def extract_red_mask(image):
    """Выделяет бледную красную сетку несколькими способами и объединяет их."""
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    red_mask_1 = cv2.inRange(hsv_image, LOWER_RED_1, UPPER_RED_1)
    red_mask_2 = cv2.inRange(hsv_image, LOWER_RED_2, UPPER_RED_2)
    hsv_red_mask = cv2.bitwise_or(red_mask_1, red_mask_2)

    red_like_mask = build_red_like_mask(image)

    if USE_LAB_RED_MASK:
        lab_a_channel, red_from_lab_mask = build_lab_red_mask(image)
    else:
        lab_a_channel = np.zeros(image.shape[:2], dtype=np.uint8)
        red_from_lab_mask = np.zeros(image.shape[:2], dtype=np.uint8)

    red_mask_combined = cv2.bitwise_or(hsv_red_mask, red_like_mask)
    red_mask_combined = cv2.bitwise_or(red_mask_combined, red_from_lab_mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (MORPH_SIZE, MORPH_SIZE))

    red_mask_after_close = cv2.morphologyEx(red_mask_combined, cv2.MORPH_CLOSE, kernel)
    red_mask_after_dilate = cv2.dilate(
        red_mask_after_close,
        kernel,
        iterations=DILATE_ITERATIONS,
    )
    red_mask_clean = cv2.morphologyEx(
        red_mask_after_dilate,
        cv2.MORPH_OPEN,
        kernel,
        iterations=OPEN_ITERATIONS,
    )

    debug_masks = {
        "red_mask_1": red_mask_1,
        "red_mask_2": red_mask_2,
        "red_like_mask": red_like_mask,
        "lab_a_channel": lab_a_channel,
        "red_from_lab_mask": red_from_lab_mask,
        "red_mask_combined_before_morph": red_mask_combined,
        "red_mask_after_close": red_mask_after_close,
        "red_mask_after_dilate": red_mask_after_dilate,
        "red_mask_clean": red_mask_clean,
    }

    return red_mask_clean, debug_masks


def build_search_roi_mask(mask):
    """Оставляет рабочую область без верхней служебной зоны и нижнего края."""
    height, width = mask.shape[:2]
    y_start = int(height * SEARCH_Y_START)
    y_end = int(height * SEARCH_Y_END)

    search_roi_mask = np.zeros((height, width), dtype=np.uint8)
    search_roi_mask[y_start:y_end, :] = mask[y_start:y_end, :]

    return search_roi_mask, y_start, y_end


def build_horizontal_emphasis_mask(mask):
    """Усиливает длинные горизонтальные структуры сетки."""
    kernel_horizontal = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (HORIZONTAL_KERNEL_WIDTH, 1),
    )
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_horizontal)


def run_hough(binary_image):
    """Запускает HoughLinesP по бинарному изображению."""
    _, width = binary_image.shape[:2]
    min_line_length = max(30, int(width * HOUGH_MIN_LINE_FRAC))

    raw_lines = cv2.HoughLinesP(
        binary_image,
        rho=1,
        theta=np.pi / 180,
        threshold=HOUGH_THRESHOLD,
        minLineLength=min_line_length,
        maxLineGap=HOUGH_MAX_LINE_GAP,
    )

    all_lines = []
    filtered_lines = []

    if raw_lines is None:
        return all_lines, filtered_lines

    for line in raw_lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        angle = normalize_angle(float(angle))

        line_info = {
            "points": (x1, y1, x2, y2),
            "angle": angle,
        }
        all_lines.append(line_info)

        if abs(angle) < ANGLE_THRESHOLD:
            filtered_lines.append(line_info)

    return all_lines, filtered_lines


def detect_lines(red_mask_clean):
    """Ищет линии по маске сетки, а при необходимости переходит к fallback через edges."""
    search_roi_mask, roi_y_start, roi_y_end = build_search_roi_mask(red_mask_clean)
    horizontal_emphasis_mask = build_horizontal_emphasis_mask(search_roi_mask)

    if np.count_nonzero(horizontal_emphasis_mask) > 0:
        hough_input_mask = horizontal_emphasis_mask
        hough_input_name = "horizontal emphasis mask"
    else:
        hough_input_mask = search_roi_mask
        hough_input_name = "cleaned red mask ROI"

    mask_all_lines, mask_filtered_lines = run_hough(hough_input_mask)

    blurred_mask = cv2.GaussianBlur(search_roi_mask, (5, 5), 0)
    edges = cv2.Canny(blurred_mask, CANNY_LOW, CANNY_HIGH)
    edge_all_lines, edge_filtered_lines = run_hough(edges)

    selected_all_lines = mask_all_lines
    selected_filtered_lines = mask_filtered_lines
    hough_mode = "mask"
    selected_input_name = hough_input_name

    if len(mask_filtered_lines) < MIN_FILTERED_LINES_WARNING and len(edge_filtered_lines) > len(mask_filtered_lines):
        selected_all_lines = edge_all_lines
        selected_filtered_lines = edge_filtered_lines
        hough_mode = "edges fallback"
        selected_input_name = "edges"

    debug_data = {
        "search_roi_mask": search_roi_mask,
        "horizontal_emphasis_mask": horizontal_emphasis_mask,
        "hough_input_mask": hough_input_mask,
        "edges": edges,
        "roi_y_start": roi_y_start,
        "roi_y_end": roi_y_end,
        "hough_mode": hough_mode,
        "hough_input_name": selected_input_name,
        "mask_raw_lines": len(mask_all_lines),
        "mask_filtered_lines": len(mask_filtered_lines),
        "edge_raw_lines": len(edge_all_lines),
        "edge_filtered_lines": len(edge_filtered_lines),
    }

    return selected_all_lines, selected_filtered_lines, debug_data


def compute_rotation_angle(filtered_lines):
    """Вычисляет средний угол по почти горизонтальным линиям."""
    if not filtered_lines:
        return 0.0

    angle_sum = 0.0
    for line in filtered_lines:
        angle_sum += line["angle"]

    return angle_sum / len(filtered_lines)


def rotate_image(image, angle):
    """Поворачивает изображение вокруг центра."""
    height, width = image.shape[:2]
    center = (width // 2, height // 2)

    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    return cv2.warpAffine(
        image,
        rotation_matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def run_stage1_pipeline(image):
    """Выполняет этап 1 и возвращает ключевые результаты в удобном виде."""
    red_mask_clean, red_debug = extract_red_mask(image)
    all_lines, filtered_lines, line_debug = detect_lines(red_mask_clean)

    angle = compute_rotation_angle(filtered_lines)
    aligned_image = rotate_image(image, -angle)
    hough_lines_all = draw_lines(image, all_lines, (0, 255, 0))
    hough_lines_filtered = draw_lines(hough_lines_all, filtered_lines, (0, 0, 255))

    return {
        "original_image": image,
        "aligned_image": aligned_image,
        "final_angle": angle,
        "red_mask_clean": red_mask_clean,
        "red_debug": red_debug,
        "line_debug": line_debug,
        "all_lines": all_lines,
        "filtered_lines": filtered_lines,
        "hough_lines_all": hough_lines_all,
        "hough_lines_filtered": hough_lines_filtered,
    }


def draw_lines(image, lines, color):
    """Рисует линии поверх изображения."""
    debug_image = image.copy()

    for line in lines:
        x1, y1, x2, y2 = line["points"]
        cv2.line(debug_image, (x1, y1), (x2, y2), color, 2)

    return debug_image


def prepare_collage_tile(image, width, height, title):
    """Подготавливает одно изображение для debug-коллажа."""
    if len(image.shape) == 2:
        tile = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        tile = image.copy()

    tile = cv2.resize(tile, (width, height), interpolation=cv2.INTER_AREA)
    cv2.putText(
        tile,
        title,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return tile


def create_debug_collage(images):
    """Собирает коллаж 3x3 из ключевых debug-изображений."""
    cell_width = 420
    cell_height = 260
    rows = []

    for row_index in range(0, len(images), 3):
        row_images = images[row_index:row_index + 3]
        tiles = []

        for title, image in row_images:
            tiles.append(prepare_collage_tile(image, cell_width, cell_height, title))

        while len(tiles) < 3:
            tiles.append(np.zeros((cell_height, cell_width, 3), dtype=np.uint8))

        rows.append(np.hstack(tiles))

    return np.vstack(rows)
