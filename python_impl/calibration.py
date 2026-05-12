import numpy as np


# TODO: подобрать x-координаты временных меток.
TIME_X0_PX = 0.0
SECONDS_PER_PIXEL = 1.0

# TODO: подобрать y-координаты шкалы FHR.
FHR_Y_TOP_PX = 0.0
FHR_VALUE_TOP = 200.0
FHR_Y_BOTTOM_PX = 1.0
FHR_VALUE_BOTTOM = 60.0

# TODO: подобрать y-координаты шкалы UA.
UA_Y_TOP_PX = 0.0
UA_VALUE_TOP = 100.0
UA_Y_BOTTOM_PX = 1.0
UA_VALUE_BOTTOM = 0.0


def load_points_csv(path):
    """Загружает CSV с колонками x_px,y_px."""
    return np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.float64)


def calibrate_time_axis(points, x0, seconds_per_pixel):
    """Добавляет к точкам временную координату в секундах."""
    calibrated = np.zeros((points.shape[0], 3), dtype=np.float64)
    calibrated[:, 0] = points[:, 0]
    calibrated[:, 1] = points[:, 1]
    calibrated[:, 2] = (points[:, 0] - x0) * seconds_per_pixel
    return calibrated


def calibrate_fhr_axis(points, y_top, value_top, y_bottom, value_bottom):
    """Переводит y верхнего графика из пикселей в bpm."""
    return calibrate_y_axis(points, y_top, value_top, y_bottom, value_bottom)


def calibrate_ua_axis(points, y_top, value_top, y_bottom, value_bottom):
    """Переводит y нижнего графика из пикселей в mmHg."""
    return calibrate_y_axis(points, y_top, value_top, y_bottom, value_bottom)


def calibrate_y_axis(points, y_top, value_top, y_bottom, value_bottom):
    """Линейно переводит пиксельную координату y в физическое значение."""
    scale = (value_bottom - value_top) / (y_bottom - y_top)
    return value_top + (points[:, 1] - y_top) * scale


def build_final_csv(upper_points, lower_points):
    """Готовит объединенную таблицу для будущего финального CSV."""
    upper_with_time = calibrate_time_axis(upper_points, TIME_X0_PX, SECONDS_PER_PIXEL)
    lower_with_time = calibrate_time_axis(lower_points, TIME_X0_PX, SECONDS_PER_PIXEL)

    upper_values = calibrate_fhr_axis(
        upper_points,
        FHR_Y_TOP_PX,
        FHR_VALUE_TOP,
        FHR_Y_BOTTOM_PX,
        FHR_VALUE_BOTTOM,
    )
    lower_values = calibrate_ua_axis(
        lower_points,
        UA_Y_TOP_PX,
        UA_VALUE_TOP,
        UA_Y_BOTTOM_PX,
        UA_VALUE_BOTTOM,
    )

    rows = []

    for index in range(upper_points.shape[0]):
        rows.append(
            {
                "signal": "fhr",
                "x_px": upper_with_time[index, 0],
                "y_px": upper_with_time[index, 1],
                "time_sec": upper_with_time[index, 2],
                "value": upper_values[index],
            }
        )

    for index in range(lower_points.shape[0]):
        rows.append(
            {
                "signal": "ua",
                "x_px": lower_with_time[index, 0],
                "y_px": lower_with_time[index, 1],
                "time_sec": lower_with_time[index, 2],
                "value": lower_values[index],
            }
        )

    return rows
