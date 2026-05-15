#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

BUILD_DIR="build/cpp"
RESULTS_DIR="results"
DEMO_DIR="demonstration plots"
CPP_BINARY="$BUILD_DIR/cpp_medical_digitizer"
EXPLANATORY_NOTE_PATH="$RESULTS_DIR/пояснительная записка.md"

log() {
    printf '\n[run_project] %s\n' "$1"
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf '[run_project][ERROR] Command not found: %s\n' "$1" >&2
        exit 1
    fi
}

python_dependencies_available() {
    "$PYTHON_BIN" - <<'PY'
import importlib.util
import sys

required_modules = {
    "numpy": "numpy",
    "opencv-python": "cv2",
    "matplotlib": "matplotlib",
}

missing = [
    package_name
    for package_name, module_name in required_modules.items()
    if importlib.util.find_spec(module_name) is None
]

if missing:
    print(", ".join(missing))
    sys.exit(1)
PY
}

generate_explanatory_note() {
    mkdir -p "$RESULTS_DIR"

    cat > "$EXPLANATORY_NOTE_PATH" <<'MD'
# Пояснительная записка к result.csv

Файл `result.csv` содержит финальный откалиброванный временной ряд, полученный из изображения КТГ-графика. Каждая строка соответствует одному отсчету на регулярной временной сетке с шагом 1 секунда.

## Столбцы CSV

| Столбец | Описание | Единицы |
| --- | --- | --- |
| `sample_idx` | Порядковый номер отсчета, начиная с 0. | - |
| `time_sec` | Время от начала восстановленного фрагмента записи. | секунды |
| `fhr_bpm` | Частота сердечных сокращений плода, восстановленная с верхнего графика. | ударов в минуту, bpm |
| `ua_kpa` | Маточная активность, восстановленная с нижнего графика. | кПа |
| `ua_mmhg` | Маточная активность, пересчитанная из `ua_kpa` в миллиметры ртутного столба. | мм рт. ст. |

## Примечания

- `time_sec` идет с шагом 1 секунда.
- Значение `NaN` означает, что для этого момента времени не было надежной восстановленной точки соответствующего сигнала.
- Столбцы `ua_kpa` и `ua_mmhg` описывают один и тот же сигнал в разных единицах измерения.
- Финальный файл для сдачи находится по пути `results/result.csv`.
MD
}

log "Checking required commands"
require_command cmake
require_command python3

if [[ -n "${PYTHON_BIN:-}" ]]; then
    require_command "$PYTHON_BIN"
elif [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
else
    log "Creating Python virtual environment in .venv"
    python3 -m venv .venv
    PYTHON_BIN=".venv/bin/python"
fi

log "Removing previous generated results"
rm -rf "$RESULTS_DIR"
rm -rf "$BUILD_DIR"
find "$DEMO_DIR" -maxdepth 1 -type f -name '*.png' -delete

if [[ "${SKIP_PIP_INSTALL:-0}" != "1" ]]; then
    if missing_dependencies="$(python_dependencies_available)"; then
        log "Python dependencies are already installed"
    else
        log "Installing missing Python dependencies: $missing_dependencies"
        "$PYTHON_BIN" -m pip install -r data/requirements.txt
    fi
else
    log "Skipping Python dependency installation"
fi

log "Running Python preprocessing and segmentation"
"$PYTHON_BIN" python/main.py

log "Running Python calibration"
"$PYTHON_BIN" python/calibration.py

log "Generating CSV explanatory note"
generate_explanatory_note

log "Generating demonstration plots"
"$PYTHON_BIN" "$DEMO_DIR/make_demonstration_plots.py"

log "Configuring C++ build"
cmake -S cpp -B "$BUILD_DIR"

log "Building C++ pipeline"
cmake --build "$BUILD_DIR"

log "Running C++ pipeline"
"./$CPP_BINARY"

log "Project run completed"
