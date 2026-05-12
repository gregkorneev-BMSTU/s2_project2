# s2_project2

Python-проект для обработки изображения КТГ-графика: выравнивания снимка по красной сетке, выделения верхнего и нижнего сигналов, сохранения пиксельных рядов и черновой калибровки в физические значения.

## Текущее состояние

Проект состоит из трех основных этапов:

1. **Предобработка и выравнивание** (`python_impl/preprocess.py`)
   - выделяет бледную красную сетку несколькими масками;
   - ищет почти горизонтальные линии через HoughLinesP;
   - оценивает угол наклона и сохраняет выровненное изображение.

2. **Сегментация сигналов** (`python_impl/segmentation.py`)
   - делит изображение на верхнюю и нижнюю панели;
   - строит маски темного сигнала;
   - очищает шум, подписи, края и служебные линии;
   - извлекает по одному `y` на каждый `x`;
   - заполняет короткие разрывы линейной интерполяцией.

3. **Калибровка** (`python_impl/calibration.py`)
   - читает `upper_points.csv` и `lower_points.csv`;
   - переводит `x_px` во время;
   - переводит верхнюю панель в `fhr_bpm`;
   - переводит нижнюю панель в `ua_kpa` и `ua_mmhg`;
   - сохраняет общий `results/python/result.csv`.

Калибровка уже реализована как рабочий каркас, но координаты временных меток и шкал пока заданы ручными константами-заглушками с `TODO`. Перед использованием чисел как финальных результатов эти точки нужно уточнить по исходному изображению.

## Структура проекта

```text
.
├── data/
│   └── input.png или input.jpg
├── python_impl/
│   ├── main.py
│   ├── preprocess.py
│   ├── segmentation.py
│   └── calibration.py
├── results/python/
│   ├── original.png
│   ├── aligned.png
│   ├── upper_panel.png
│   ├── lower_panel.png
│   ├── result.csv
│   └── debug/
├── log.md
└── README.md
```

## Зависимости

Нужен Python 3 и пакеты:

```bash
pip install numpy opencv-python matplotlib
```

`matplotlib` используется только для debug-графиков калибровки. Если он не установлен, `calibration.py` использует fallback-отрисовку через OpenCV.

## Входные данные

Основной входной файл:

```text
data/input.jpg
```

Если `data/input.jpg` не найден, `python_impl/main.py` автоматически попробует открыть:

```text
data/input.png
```

## Запуск

Из корня проекта:

```bash
python python_impl/main.py
```

Команда выполняет этапы 1 и 2:

- сохраняет исходник и выровненное изображение;
- разрезает изображение на панели;
- строит маски и overlay для проверки качества;
- сохраняет пиксельные ряды:
  - `results/python/debug/upper_points.csv`
  - `results/python/debug/lower_points.csv`

После этого можно запустить калибровку:

```bash
python python_impl/calibration.py
```

Она создаст:

- `results/python/result.csv`
- `results/python/debug/calibrated_fhr_plot.png`
- `results/python/debug/calibrated_ua_plot.png`

## Основные результаты

Ключевые файлы в `results/python/`:

- `original.png` - загруженное входное изображение;
- `aligned.png` - изображение после коррекции наклона;
- `upper_panel.png` - верхняя панель графика;
- `lower_panel.png` - нижняя панель графика;
- `result.csv` - объединенный временной ряд после калибровки.

Ключевые debug-файлы в `results/python/debug/`:

- `debug_collage.png` - коллаж основных масок и линий этапа 1;
- `original_vs_aligned_diff.png` - усиленная разница между исходником и выровненной версией;
- `upper_signal_overlay.png` и `lower_signal_overlay.png` - наложение найденных сигналов на панели;
- `upper_trace_only.png` и `lower_trace_only.png` - только извлеченные трассы;
- `upper_points_raw.csv` и `lower_points_raw.csv` - сырые точки до интерполяции;
- `upper_points_interpolated.csv` и `lower_points_interpolated.csv` - точки после интерполяции;
- `calibrated_fhr_plot.png` и `calibrated_ua_plot.png` - debug-графики откалиброванных рядов.

## Формат CSV

Пиксельные ряды:

```csv
x_px,y_px
216,333
217,334
```

Финальный `result.csv`:

```csv
sample_idx,time_sec,fhr_bpm,ua_kpa,ua_mmhg
0,0.000000,150.000000,NaN,NaN
```

Значения `NaN` означают, что в конкретный момент есть точка только одной из панелей.

## Проверка кода

Минимальная проверка синтаксиса:

```bash
python -m py_compile python_impl/main.py python_impl/segmentation.py python_impl/preprocess.py python_impl/calibration.py
```

## Ограничения и ближайшие задачи

- Уточнить ручные калибровочные точки в `python_impl/calibration.py`.
- Добавить автоматическое распознавание шкал и временных меток.
- Вынести зависимости в `requirements.txt`.
- Добавить тестовые проверки для функций калибровки и трассировки.
