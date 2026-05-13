#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

BUILD_DIR="build/cpp"
RESULTS_DIR="results"
DEMO_DIR="demonstration plots"
CPP_BINARY="$BUILD_DIR/cpp_medical_digitizer"

log() {
    printf '\n[run_project] %s\n' "$1"
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf '[run_project][ERROR] Command not found: %s\n' "$1" >&2
        exit 1
    fi
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
    log "Installing Python dependencies from data/requirements.txt"
    "$PYTHON_BIN" -m pip install -r data/requirements.txt
else
    log "Skipping Python dependency installation"
fi

log "Running Python preprocessing and segmentation"
"$PYTHON_BIN" python_impl/main.py

log "Running Python calibration"
"$PYTHON_BIN" python_impl/calibration.py

log "Generating demonstration plots"
"$PYTHON_BIN" "$DEMO_DIR/make_demonstration_plots.py"

log "Configuring C++ build"
cmake -S cpp_impl -B "$BUILD_DIR"

log "Building C++ pipeline"
cmake --build "$BUILD_DIR"

log "Running C++ pipeline"
"./$CPP_BINARY"

log "Project run completed"
