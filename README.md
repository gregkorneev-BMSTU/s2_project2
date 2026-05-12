# s2_project2

Проект для обработки изображения КТГ-графика: выравнивания снимка по красной сетке, выделения верхнего и нижнего сигналов, сохранения пиксельных рядов и ручной калибровки в физические значения.

Основная рабочая реализация сейчас находится в `python_impl/`. Дополнительно добавлен C++-прототип этапа 1 в `cpp_impl/`: он повторяет выделение красной сетки, поиск горизонтальных линий, расчет угла и сохранение выровненного изображения.

## Текущее состояние

Python-пайплайн состоит из трех основных этапов:

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
   - сохраняет регулярный общий ряд `results/python/result.csv`.

Калибровочные координаты задаются вручную в `python_impl/calibration.py` по проверочным изображениям `upper_calibration_marks.png`, `lower_calibration_marks.png` и `time_calibration_marks.png`.

C++-часть пока покрывает только первый этап: загрузку `data/input.jpg` или `data/input.png`, выделение сетки, Hough-поиск горизонталей, расчет угла и сохранение debug-артефактов в `results/cpp/`.

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
├── cpp_impl/
│   ├── CMakeLists.txt
│   ├── include/
│   │   └── preprocess.hpp
│   └── src/
│       ├── main.cpp
│       └── preprocess.cpp
├── results/python/
│   ├── original.png
│   ├── aligned.png
│   ├── upper_panel.png
│   ├── lower_panel.png
│   ├── result.csv
│   ├── result_sparse.csv
│   ├── fhr_timeseries.csv
│   ├── ua_timeseries.csv
│   ├── calibration_params.txt
│   └── debug/
├── results/cpp/
│   ├── original.png
│   ├── aligned.png
│   └── debug/
├── log.md
└── README.md
```

## Зависимости

Для Python нужны Python 3 и пакеты:

```bash
pip install numpy opencv-python matplotlib
```

`matplotlib` используется только для debug-графиков калибровки. Если он не установлен, `calibration.py` использует fallback-отрисовку через OpenCV.

Для C++-версии нужны:

- компилятор с поддержкой C++17;
- CMake 3.12+;
- OpenCV для C++.

## Входные данные

Основной входной файл:

```text
data/input.jpg
```

Если `data/input.jpg` не найден, `python_impl/main.py` автоматически попробует открыть:

```text
data/input.png
```

## Запуск Python-пайплайна

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

После этого запустить калибровку:

```bash
python python_impl/calibration.py
```

Она создаст:

- `results/python/result.csv`
- `results/python/result_sparse.csv`
- `results/python/fhr_timeseries.csv`
- `results/python/ua_timeseries.csv`
- `results/python/calibration_params.txt`
- `results/python/debug/calibrated_fhr_plot.png`
- `results/python/debug/calibrated_ua_plot.png`
- `results/python/debug/upper_calibration_marks.png`
- `results/python/debug/lower_calibration_marks.png`
- `results/python/debug/time_calibration_marks.png`

## Запуск C++-этапа 1

Из корня проекта:

```bash
cmake -S cpp_impl -B build/cpp
cmake --build build/cpp
./build/cpp/cpp_medical_digitizer
```

Также исполняемый файл можно запускать из `cpp_impl/`; код сам определяет, где находится корень проекта.

C++-запуск создаст:

- `results/cpp/original.png`
- `results/cpp/aligned.png`
- `results/cpp/debug/rotation.txt`
- debug-маски красной сетки;
- debug-изображения Hough-линий.

## Основные результаты

Ключевые файлы в `results/python/`:

- `original.png` - загруженное входное изображение;
- `aligned.png` - изображение после коррекции наклона;
- `upper_panel.png` - верхняя панель графика;
- `lower_panel.png` - нижняя панель графика;
- `result.csv` - регулярный объединенный временной ряд после калибровки с шагом 1 секунда;
- `result_sparse.csv` - старое точное объединение рядов без регулярной сетки;
- `fhr_timeseries.csv` - отдельный откалиброванный ряд FHR;
- `ua_timeseries.csv` - отдельный откалиброванный ряд UA;
- `calibration_params.txt` - параметры ручной калибровки и итоговые диапазоны значений.

Ключевые debug-файлы в `results/python/debug/`:

- `debug_collage.png` - коллаж основных масок и линий этапа 1;
- `original_vs_aligned_diff.png` - усиленная разница между исходником и выровненной версией;
- `upper_signal_overlay.png` и `lower_signal_overlay.png` - наложение найденных сигналов на панели;
- `upper_trace_only.png` и `lower_trace_only.png` - только извлеченные трассы;
- `upper_points_raw.csv` и `lower_points_raw.csv` - сырые точки до интерполяции;
- `upper_points_interpolated.csv` и `lower_points_interpolated.csv` - точки после интерполяции;
- `upper_calibration_marks.png`, `lower_calibration_marks.png`, `time_calibration_marks.png` - проверка ручных калибровочных опор;
- `calibrated_fhr_plot.png` и `calibrated_ua_plot.png` - debug-графики откалиброванных рядов.

Ключевые файлы C++-этапа в `results/cpp/`:

- `original.png` - загруженное входное изображение;
- `aligned.png` - изображение после коррекции наклона;
- `debug/rotation.txt` - угол поворота и количество найденных линий;
- `debug/hough_lines_all.png` и `debug/hough_lines_filtered.png` - все найденные линии и отфильтрованные горизонтали;
- `debug/red_mask_clean.png` - итоговая маска красной сетки.

## Формат CSV

Пиксельные ряды:

```csv
x_px,y_px
216,333
217,334
```

Финальный регулярный `result.csv`:

```csv
sample_idx,time_sec,fhr_bpm,ua_kpa,ua_mmhg
0,0.000000,150.000000,NaN,NaN
1,1.000000,150.100000,1.200000,9.000744
```

Значения `NaN` означают, что в конкретный момент нет надежной точки для одной из панелей или ближайшие исходные точки дальше допустимого интерполяционного разрыва.

## Проверка кода

Минимальная проверка синтаксиса:

```bash
python -m py_compile python_impl/main.py python_impl/segmentation.py python_impl/preprocess.py python_impl/calibration.py
```

Минимальная проверка сборки C++:

```bash
cmake -S cpp_impl -B build/cpp
cmake --build build/cpp
```

## Ограничения и ближайшие задачи

- Довести C++-реализацию до этапов сегментации и калибровки.
- Добавить автоматическое распознавание шкал и временных меток.
- Вынести зависимости в `requirements.txt`.
- Добавить тестовые проверки для функций калибровки и трассировки.
