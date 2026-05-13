# Demonstration plots

Эта папка содержит отдельную проверочную визуализацию координат, извлеченных из КТГ-графика.

Запуск из корня проекта:

```bash
python3 "demonstration plots/make_demonstration_plots.py"
```

Скрипт читает:

- `results/python/debug/upper_points.csv`
- `results/python/debug/lower_points.csv`
- `results/python/upper_panel.png`
- `results/python/lower_panel.png`
- `results/python/fhr_timeseries.csv`
- `results/python/ua_timeseries.csv`

И создает в этой папке:

- `upper_trace_from_coordinates.png` и `lower_trace_from_coordinates.png` - чистые линии, восстановленные только из координат `x_px,y_px` в той же пиксельной системе, что и исходные панели;
- `upper_trace_overlay.png` и `lower_trace_overlay.png` - те же координаты, наложенные поверх исходных панелей;
- `calibrated_timeseries.png` - откалиброванные FHR и UA по времени;
- `demonstration_summary.png` - сводное изображение для быстрой визуальной проверки: две строки соответствуют двум исходным графикам, FHR и UA; слева координаты наложены на исходную панель, справа показана линия, восстановленная только из координат.
