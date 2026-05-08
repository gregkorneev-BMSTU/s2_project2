# Log

## 2026-05-05 14:56:41 MSK — Структура результатов и старт этапа 2

- Добавлена и проверена Python-реализация этапа 1: выделение бледной красной сетки, поиск горизонтальных линий, оценка угла и сохранение `aligned.png`.
- Создана структура результатов `results/python/` и подпапка `results/python/debug/`.
- Основные файлы оставлены в `results/python/`: `original.png`, `aligned.png`, `upper_panel.png`, `lower_panel.png`.
- Все промежуточные debug-файлы перенесены в `results/python/debug/`.
- Добавлен старт этапа 2 в `python_impl/segmentation.py`: разбиение на верхнюю и нижнюю панели, raw/clean-маски сигнала и overlay для проверки линий.
- Проект перезапущен через `.venv/bin/python python_impl/main.py`.
- Последний проверенный результат: угол поворота `-0.71` градуса, найдено `1099` горизонтальных линий.

## 2026-05-05 14:58:19 MSK — Проверка выравнивания

- Перепроверен этап 1 после вопроса о том, почему `aligned.png` визуально почти не отличается от исходника.
- Проект повторно запущен через `.venv/bin/python python_impl/main.py`.
- Подтверждено, что поворот применяется: угол `-0.71` градуса, найдено `1099` горизонтальных линий.
- Сохранена усиленная карта отличий `results/python/debug/original_vs_aligned_diff.png`.
- Причина слабого визуального отличия: исходное изображение уже почти ровное, а коррекция меньше одного градуса.

## 2026-05-08 15:09:00 MSK — Этап 2: очистка масок и пиксельные ряды

- Проверены `upper_signal_overlay.png`, `lower_signal_overlay.png`, `upper_clean_mask.png` и `lower_clean_mask.png`.
- Маски в целом попадают на черную линию графика, но в верхней панели был заметен правый краевой артефакт, а мелкие компоненты могли мешать выбору точки по столбцу.
- В `python_impl/segmentation.py` усилена `clean_signal_mask()`: добавлена фильтрация компонентов по площади, ширине, высоте, удаление узких высоких артефактов у правого края и мелких компонентов в верхней зоне панели.
- Добавлена более устойчивая `extract_trace_points()`: для каждого `x` выбирается `y`, ближайший к предыдущему значению, а короткие пропуски заполняются линейной интерполяцией.
- В `python_impl/main.py` добавлено сохранение CSV с пиксельными рядами `x_px,y_px`.
- Проект перезапущен через `.venv/bin/python python_impl/main.py`, debug-файлы пересохранены.
- Созданы `results/python/debug/upper_points.csv` и `results/python/debug/lower_points.csv`.
- Последний проверенный результат: `upper_clean_mask` содержит `59415` пикселей и `2079` точек, `lower_clean_mask` содержит `41309` пикселей и `2260` точек.
- Финальная калибровка пока не выполнялась; текущая цель этапа — качественные пиксельные ряды `x_px,y_px`.

## 2026-05-08 15:10:00 MSK — Этап 2: исправление нижней панели

- Найдена проблема в `lower_signal_overlay.png`: справа снизу алгоритм захватывал длинный почти горизонтальный участок около подписи `UA 0 mmHg` и нижней оси.
- В `python_impl/segmentation.py` добавлен режим `panel_type` для `analyze_panel(panel_image, panel_type)` и `clean_signal_mask(mask, panel_type)`.
- В `python_impl/main.py` вызовы разделены на `analyze_panel(upper_panel, "upper")` и `analyze_panel(lower_panel, "lower")`.
- Для нижней панели добавлена граница рабочей области `LOWER_SIGNAL_Y_END_FRACTION = 0.86`; всё ниже этой границы обнуляется в clean-маске.
- Для lower-панели добавлена фильтрация длинных нижних горизонтальных компонентов и мелких текстовых компонентов справа снизу.
- Дополнительно добавлено удаление нижних горизонтальных артефактов через морфологическое выделение горизонталей, чтобы убрать служебную линию даже при склейке с высоким скачком.
- В `lower_signal_overlay.png` добавлена синяя линия границы рабочей области.
- Сохранены новые debug-файлы: `lower_clean_before_roi_cut.png`, `lower_clean_after_roi_cut.png`, `lower_removed_components_debug.png`.
- Проект перезапущен через `.venv/bin/python python_impl/main.py`, debug-файлы и CSV пересохранены.
- Последний проверенный результат: `upper_points.csv` содержит `2079` точек (`x=216..2517`), `lower_points.csv` содержит `982` точки (`x=235..1926`).
- Для нижней панели было `2272` точек до cleanup и стало `982` точки после cleanup; `lower_clean_mask` содержит `26621` белый пиксель.
- Проверка `.venv/bin/python -m py_compile python_impl/main.py python_impl/segmentation.py` прошла успешно.
- Финальная калибровка по-прежнему не выполнялась.

## 2026-05-08 16:03:45 MSK — Этап 2: устойчивые маски и трассировка

- Этап 1 не изменялся: `python_impl/preprocess.py`, параметры Hough и red mask для выравнивания не трогались.
- В `python_impl/segmentation.py` переработана компонентная фильтрация этапа 2: добавлены общие правила для мелкого шума, маленьких квадратных компонент и тонких широких горизонтальных элементов.
- Для верхней панели добавлены отдельные правила удаления мелких компонент в зоне верхних подписей, нижней границы и коротких шумовых фрагментов без удаления высоких вертикальных скачков.
- Для нижней панели сохранен ROI-cut `LOWER_SIGNAL_Y_END_FRACTION = 0.86`, усилена фильтрация нижних горизонтальных служебных линий, правых нижних текстовых компонент и маленького шума.
- `extract_trace_points(mask, panel_type)` теперь строит raw-трассу с ограничением скачка: `MAX_JUMP_UPPER = 80`, `MAX_JUMP_LOWER = 100`; при слишком большом скачке столбец считается пропуском.
- Добавлена `interpolate_small_gaps(points, max_gap)`: короткие разрывы заполняются линейно, большие разрывы остаются разрывами.
- Текущие `upper_points.csv` и `lower_points.csv` теперь содержат интерполированные ряды; дополнительно сохранены `upper_points_raw.csv`, `upper_points_interpolated.csv`, `lower_points_raw.csv`, `lower_points_interpolated.csv`.
- Добавлены debug-файлы компонент: `upper_mask_before_components.png`, `lower_mask_before_components.png`, `upper_components_kept.png`, `lower_components_kept.png`, `upper_components_removed.png`, `lower_components_removed.png`.
- Добавлены debug-файлы трассы: `upper_trace_only.png` и `lower_trace_only.png`.
- Overlay обновлен: зеленым показана clean mask, красной линией трасса, желтыми точками интерполированные точки; нижняя панель сохраняет синюю линию границы рабочей области.
- В `python_impl/main.py` добавлен вывод метрик этапа 2: компоненты до/после, удаленные компоненты, raw/interpolated points, большие разрывы и coverage по ширине.
- Проект перезапущен через `.venv/bin/python python_impl/main.py`; debug-файлы и CSV пересохранены.
- Последний проверенный результат: `upper_clean_mask` содержит `59557` белых пикселей, компоненты `33 -> 27`, raw/interpolated points `2017 -> 2132`, coverage `83.54%`.
- Последний проверенный результат: `lower_clean_mask` содержит `26679` белых пикселей, компоненты `18 -> 13`, raw/interpolated points `968 -> 1024`, coverage `40.13%`; предупреждение о низком coverage ожидаемо из-за обрезки служебной нижней зоны.
- CSV-диапазоны: `upper_points.csv` содержит `2132` точки (`x=216..2517`, `y=333..1019`), `lower_points.csv` содержит `1024` точки (`x=225..1926`, `y=95..607`).
- Проверка `.venv/bin/python -m py_compile python_impl/main.py python_impl/segmentation.py` прошла успешно.
- Финальная калибровка физических величин не выполнялась.

## 2026-05-08 16:18:38 MSK — Этап 2: мягкая нижняя маска UA

- Этап 1 не изменялся: `python_impl/preprocess.py`, выравнивание, Hough и red mask не трогались.
- Исправлена слишком жесткая обрезка нижней панели: `LOWER_SIGNAL_Y_END_FRACTION` изменен с `0.86` на `0.93`.
- Для сравнения добавлен strict-режим с прежней границей `LOWER_SIGNAL_Y_END_FRACTION_STRICT = 0.86`; рабочим режимом для `lower_points.csv` выбран soft.
- В `python_impl/segmentation.py` добавлен `cleanup_mode` для lower strict/soft очистки.
- Для soft lower-маски сохранены реальные baseline-компоненты, если они низко расположены, но имеют `height >= 10` и `area >= 30`.
- Нижние служебные горизонтали теперь удаляются точечно: `aspect_ratio > 12`, `height <= 6`, `width > 0.10 * panel_width`, `y > 0.70 * panel_height`.
- Для lower-трассировки увеличены `LOWER_MAX_INTERPOLATION_GAP` до `45` и `TRACE_GAP_LIMIT_LOWER` до `50`; baseline-кандидат не отбрасывается только из-за резкого перехода после разрыва.
- В `python_impl/main.py` добавлено сохранение `lower_clean_mask_strict.png`, `lower_clean_mask_soft.png`, `lower_signal_overlay_strict.png`, `lower_signal_overlay_soft.png`.
- Добавлен вывод `[INFO] Lower trace coverage strict`, `[INFO] Lower trace coverage soft`, `[INFO] Lower selected mode: soft`; warning выводится, если soft coverage ниже `55%`.
- Проект перезапущен через `.venv/bin/python python_impl/main.py`, debug-файлы и CSV пересохранены.
- Последний проверенный результат: lower strict coverage `59.64%`, lower soft coverage `81.11%`, выбран режим `soft`.
- `lower_points.csv` теперь содержит `2070` точек (`x=225..2384`, `y=93..657`), baseline-участки около нуля восстановлены.
- `upper_points.csv` остался на `2132` точках (`x=216..2517`, `y=333..1019`).
- Проверка `.venv/bin/python -m py_compile python_impl/main.py python_impl/segmentation.py` прошла успешно.
- Финальная калибровка физических величин не выполнялась.
