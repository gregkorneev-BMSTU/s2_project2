#include "calibration.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

const std::vector<std::pair<double, std::string>> TIME_MARKS = {
    {216.0, "09:04:38"},
    {795.0, "09:08:38"},
    {1374.0, "09:12:38"},
    {1953.0, "09:16:38"},
};

constexpr double FHR_TOP_Y = 70.0;
constexpr double FHR_BOTTOM_Y = 1040.0;
constexpr double FHR_TOP_VALUE = 200.0;
constexpr double FHR_BOTTOM_VALUE = 60.0;

constexpr double UA_TOP_Y = 127.0;
constexpr double UA_BOTTOM_Y = 657.0;
constexpr double UA_TOP_KPA = 12.0;
constexpr double UA_BOTTOM_KPA = 0.0;

constexpr double KPA_TO_MMHG = 7.50062;
constexpr double OUTPUT_DT_SEC = 1.0;
constexpr double MAX_INTERP_GAP_SEC_FHR = 15.0;
constexpr double MAX_INTERP_GAP_SEC_UA = 20.0;

double nanValue() {
    return std::numeric_limits<double>::quiet_NaN();
}

void ensureParentDir(const std::string& path) {
    const std::filesystem::path parent = std::filesystem::path(path).parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent);
    }
}

int parseTimeString(const std::string& timeString) {
    std::stringstream stream(timeString);
    std::string part;
    std::vector<int> parts;

    while (std::getline(stream, part, ':')) {
        parts.push_back(std::stoi(part));
    }

    if (parts.size() != 3) {
        throw std::runtime_error("Invalid time string: " + timeString);
    }

    return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

std::string formatFloat(double value) {
    if (std::isnan(value)) {
        return "NaN";
    }
    if (std::abs(value) < 0.5e-6) {
        return "0.000000";
    }

    std::ostringstream stream;
    stream << std::fixed << std::setprecision(6) << value;
    return stream.str();
}

std::string formatRange(const std::vector<double>& values) {
    double minValue = std::numeric_limits<double>::infinity();
    double maxValue = -std::numeric_limits<double>::infinity();
    bool hasFinite = false;

    for (double value : values) {
        if (!std::isfinite(value)) {
            continue;
        }
        minValue = std::min(minValue, value);
        maxValue = std::max(maxValue, value);
        hasFinite = true;
    }

    if (!hasFinite) {
        return "NaN..NaN";
    }

    std::ostringstream stream;
    stream << std::fixed << std::setprecision(3) << minValue << ".." << maxValue;
    return stream.str();
}

std::vector<double> traceValues(const std::vector<CalibratedPoint>& trace) {
    std::vector<double> values;
    values.reserve(trace.size());
    for (const CalibratedPoint& point : trace) {
        values.push_back(point.value);
    }
    return values;
}

std::vector<double> uaMmhgValues(const std::vector<CalibratedPoint>& uaTrace) {
    std::vector<double> values;
    values.reserve(uaTrace.size());
    for (const CalibratedPoint& point : uaTrace) {
        values.push_back(pixelToUaMmhg(point.value));
    }
    return values;
}

double maxTraceTime(const std::vector<CalibratedPoint>& trace) {
    if (trace.empty()) {
        return 0.0;
    }

    double maxTime = trace.front().timeSec;
    for (const CalibratedPoint& point : trace) {
        if (std::isfinite(point.timeSec)) {
            maxTime = std::max(maxTime, point.timeSec);
        }
    }
    return maxTime;
}

std::vector<CalibratedPoint> sortedUniqueTrace(const std::vector<CalibratedPoint>& trace) {
    std::vector<CalibratedPoint> sorted = trace;
    std::sort(sorted.begin(), sorted.end(), [](const CalibratedPoint& left, const CalibratedPoint& right) {
        return left.timeSec < right.timeSec;
    });

    std::vector<CalibratedPoint> unique;
    size_t index = 0;
    while (index < sorted.size()) {
        const double timeSec = sorted[index].timeSec;
        double sum = 0.0;
        int count = 0;

        while (index < sorted.size() && sorted[index].timeSec == timeSec) {
            sum += sorted[index].value;
            ++count;
            ++index;
        }

        unique.push_back({timeSec, sum / std::max(1, count)});
    }

    return unique;
}

std::vector<double> interpolateTraceToGrid(
    const std::vector<CalibratedPoint>& trace,
    const std::vector<double>& timeGrid,
    double maxGapSec
) {
    std::vector<double> result(timeGrid.size(), nanValue());
    if (trace.empty() || timeGrid.empty()) {
        return result;
    }

    const std::vector<CalibratedPoint> unique = sortedUniqueTrace(trace);
    std::vector<double> times;
    times.reserve(unique.size());
    for (const CalibratedPoint& point : unique) {
        times.push_back(point.timeSec);
    }

    for (size_t gridIndex = 0; gridIndex < timeGrid.size(); ++gridIndex) {
        const double timeSec = timeGrid[gridIndex];
        const auto rightIt = std::lower_bound(times.begin(), times.end(), timeSec);
        const auto leftIt = std::upper_bound(times.begin(), times.end(), timeSec);

        if (rightIt == times.end() || leftIt == times.begin()) {
            continue;
        }

        const size_t rightIndex = static_cast<size_t>(rightIt - times.begin());
        const size_t leftIndex = static_cast<size_t>((leftIt - times.begin()) - 1);
        const double leftDistance = timeSec - unique[leftIndex].timeSec;
        const double rightDistance = unique[rightIndex].timeSec - timeSec;

        if (leftDistance > maxGapSec || rightDistance > maxGapSec) {
            continue;
        }

        const double leftTime = unique[leftIndex].timeSec;
        const double rightTime = unique[rightIndex].timeSec;
        const double leftValue = unique[leftIndex].value;
        const double rightValue = unique[rightIndex].value;

        if (std::abs(rightTime - leftTime) < 1e-12) {
            result[gridIndex] = leftValue;
        } else {
            const double ratio = (timeSec - leftTime) / (rightTime - leftTime);
            result[gridIndex] = leftValue + (rightValue - leftValue) * ratio;
        }
    }

    return result;
}

int countNanFhr(const std::vector<ResultRow>& rows) {
    int count = 0;
    for (const ResultRow& row : rows) {
        if (std::isnan(row.fhrBpm)) {
            ++count;
        }
    }
    return count;
}

int countNanUaKpa(const std::vector<ResultRow>& rows) {
    int count = 0;
    for (const ResultRow& row : rows) {
        if (std::isnan(row.uaKpa)) {
            ++count;
        }
    }
    return count;
}

int countNanUaMmhg(const std::vector<ResultRow>& rows) {
    int count = 0;
    for (const ResultRow& row : rows) {
        if (std::isnan(row.uaMmhg)) {
            ++count;
        }
    }
    return count;
}

void warnIfRangeOutside(
    const std::string& name,
    const std::vector<double>& values,
    double minAllowed,
    double maxAllowed
) {
    double minValue = std::numeric_limits<double>::infinity();
    double maxValue = -std::numeric_limits<double>::infinity();
    bool hasFinite = false;

    for (double value : values) {
        if (!std::isfinite(value)) {
            continue;
        }
        minValue = std::min(minValue, value);
        maxValue = std::max(maxValue, value);
        hasFinite = true;
    }

    if (!hasFinite) {
        std::cout << "[WARN] " << name << " has no finite values\n";
        return;
    }

    if (minValue < minAllowed || maxValue > maxAllowed) {
        std::cout << std::fixed << std::setprecision(3);
        std::cout << "[WARN] " << name << " outside expected range "
                  << std::setprecision(1) << minAllowed << ".." << maxAllowed << ": "
                  << std::setprecision(3) << minValue << ".." << maxValue << "\n";
    }
}

void warnIfManyNegativeTimes(
    const std::vector<CalibratedPoint>& fhrTrace,
    const std::vector<CalibratedPoint>& uaTrace
) {
    const int totalCount = static_cast<int>(fhrTrace.size() + uaTrace.size());
    if (totalCount == 0) {
        return;
    }

    int negativeCount = 0;
    for (const CalibratedPoint& point : fhrTrace) {
        if (point.timeSec < -1e-6) {
            ++negativeCount;
        }
    }
    for (const CalibratedPoint& point : uaTrace) {
        if (point.timeSec < -1e-6) {
            ++negativeCount;
        }
    }

    const int warningLimit = std::max(10, static_cast<int>(totalCount * 0.01));
    if (negativeCount > warningLimit) {
        std::cout << "[WARN] Many negative time_sec values: "
                  << negativeCount << "/" << totalCount << "\n";
    }
}

}  // namespace

std::vector<TracePoint> loadTraceCsv(const std::string& path) {
    std::ifstream csvFile(path);
    if (!csvFile.is_open()) {
        throw std::runtime_error("Cannot open trace CSV: " + path);
    }

    std::vector<TracePoint> points;
    std::string line;
    std::getline(csvFile, line);

    while (std::getline(csvFile, line)) {
        if (line.empty()) {
            continue;
        }

        std::stringstream stream(line);
        std::string xText;
        std::string yText;
        if (!std::getline(stream, xText, ',') || !std::getline(stream, yText, ',')) {
            continue;
        }

        points.push_back({std::stod(xText), std::stod(yText)});
    }

    return points;
}

double computeSecondsPerPixel(double* x0Out) {
    if (TIME_MARKS.size() < 2) {
        throw std::runtime_error("At least two time marks are required");
    }

    std::vector<std::pair<double, std::string>> sortedMarks = TIME_MARKS;
    std::sort(sortedMarks.begin(), sortedMarks.end(), [](const auto& left, const auto& right) {
        return left.first < right.first;
    });

    std::vector<double> xValues;
    std::vector<double> elapsedSeconds;
    xValues.reserve(sortedMarks.size());
    elapsedSeconds.reserve(sortedMarks.size());

    double previousSeconds = static_cast<double>(parseTimeString(sortedMarks.front().second));
    const double firstSeconds = previousSeconds;

    for (size_t index = 0; index < sortedMarks.size(); ++index) {
        double seconds = static_cast<double>(parseTimeString(sortedMarks[index].second));
        while (seconds < previousSeconds) {
            seconds += 24.0 * 60.0 * 60.0;
        }

        xValues.push_back(sortedMarks[index].first);
        elapsedSeconds.push_back(seconds - firstSeconds);
        previousSeconds = seconds;
    }

    double sumX = 0.0;
    double sumY = 0.0;
    double sumXX = 0.0;
    double sumXY = 0.0;
    const double n = static_cast<double>(xValues.size());

    for (size_t index = 0; index < xValues.size(); ++index) {
        sumX += xValues[index];
        sumY += elapsedSeconds[index];
        sumXX += xValues[index] * xValues[index];
        sumXY += xValues[index] * elapsedSeconds[index];
    }

    const double denominator = n * sumXX - sumX * sumX;
    if (std::abs(denominator) < 1e-12) {
        throw std::runtime_error("Time marks have degenerate x coordinates");
    }

    const double secondsPerPixel = (n * sumXY - sumX * sumY) / denominator;
    const double intercept = (sumY - secondsPerPixel * sumX) / n;
    if (secondsPerPixel <= 0.0) {
        throw std::runtime_error("Time marks must produce a positive seconds_per_pixel");
    }

    if (x0Out != nullptr) {
        *x0Out = -intercept / secondsPerPixel;
    }

    return secondsPerPixel;
}

double pixelToFhr(double yPx) {
    const double scale = (FHR_BOTTOM_VALUE - FHR_TOP_VALUE) / (FHR_BOTTOM_Y - FHR_TOP_Y);
    return FHR_TOP_VALUE + (yPx - FHR_TOP_Y) * scale;
}

double pixelToUaKpa(double yPx) {
    const double scale = (UA_BOTTOM_KPA - UA_TOP_KPA) / (UA_BOTTOM_Y - UA_TOP_Y);
    return UA_TOP_KPA + (yPx - UA_TOP_Y) * scale;
}

double pixelToUaMmhg(double uaKpa) {
    return uaKpa * KPA_TO_MMHG;
}

std::vector<CalibratedPoint> calibrateTrace(
    const std::vector<TracePoint>& points,
    double x0,
    double secondsPerPixel,
    double (*valueConverter)(double)
) {
    std::vector<CalibratedPoint> calibrated;
    calibrated.reserve(points.size());

    for (const TracePoint& point : points) {
        calibrated.push_back({
            (point.xPx - x0) * secondsPerPixel,
            valueConverter(point.yPx),
        });
    }

    return calibrated;
}

std::vector<ResultRow> mergeTimeSeries(
    const std::vector<CalibratedPoint>& fhrTrace,
    const std::vector<CalibratedPoint>& uaTrace
) {
    const double maxTime = std::max(maxTraceTime(fhrTrace), maxTraceTime(uaTrace));
    if (maxTime <= 0.0) {
        return {};
    }

    const double endTime = std::floor(maxTime / OUTPUT_DT_SEC) * OUTPUT_DT_SEC;
    std::vector<double> timeGrid;
    for (double timeSec = 0.0; timeSec <= endTime + OUTPUT_DT_SEC * 0.5; timeSec += OUTPUT_DT_SEC) {
        timeGrid.push_back(timeSec);
    }

    const std::vector<double> fhrValues =
        interpolateTraceToGrid(fhrTrace, timeGrid, MAX_INTERP_GAP_SEC_FHR);
    const std::vector<double> uaKpaValues =
        interpolateTraceToGrid(uaTrace, timeGrid, MAX_INTERP_GAP_SEC_UA);

    std::vector<ResultRow> rows;
    rows.reserve(timeGrid.size());
    for (size_t index = 0; index < timeGrid.size(); ++index) {
        const double uaMmhg = std::isnan(uaKpaValues[index]) ? nanValue() : pixelToUaMmhg(uaKpaValues[index]);
        rows.push_back({
            static_cast<int>(index),
            timeGrid[index],
            fhrValues[index],
            uaKpaValues[index],
            uaMmhg,
        });
    }

    return rows;
}

void saveResultCsv(const std::string& path, const std::vector<ResultRow>& rows) {
    ensureParentDir(path);

    std::ofstream csvFile(path);
    csvFile << "sample_idx,time_sec,fhr_bpm,ua_kpa,ua_mmhg\n";
    for (const ResultRow& row : rows) {
        csvFile << row.sampleIdx << ","
                << formatFloat(row.timeSec) << ","
                << formatFloat(row.fhrBpm) << ","
                << formatFloat(row.uaKpa) << ","
                << formatFloat(row.uaMmhg) << "\n";
    }
}

void saveCalibrationParams(
    const std::string& path,
    double x0,
    double secondsPerPixel,
    const std::vector<CalibratedPoint>& fhrTrace,
    const std::vector<CalibratedPoint>& uaTrace,
    const std::vector<ResultRow>& rows
) {
    ensureParentDir(path);

    const double resultDuration = rows.empty() ? 0.0 : rows.back().timeSec - rows.front().timeSec;
    const std::vector<double> fhrValues = traceValues(fhrTrace);
    const std::vector<double> uaKpaValues = traceValues(uaTrace);
    const std::vector<double> uaMmhg = uaMmhgValues(uaTrace);

    std::ofstream paramsFile(path);
    paramsFile << std::fixed;
    paramsFile << "Calibration parameters\n";
    paramsFile << "======================\n\n";
    paramsFile << "TIME_MARKS:\n";
    for (const auto& mark : TIME_MARKS) {
        paramsFile << "  " << std::setprecision(3) << mark.first << ", " << mark.second << "\n";
    }
    paramsFile << "\n";
    paramsFile << "x0_px: " << std::setprecision(6) << x0 << "\n";
    paramsFile << "seconds_per_pixel: " << std::setprecision(9) << secondsPerPixel << "\n";
    paramsFile << "OUTPUT_DT_SEC: " << std::setprecision(6) << OUTPUT_DT_SEC << "\n";
    paramsFile << "MAX_INTERP_GAP_SEC_FHR: " << MAX_INTERP_GAP_SEC_FHR << "\n";
    paramsFile << "MAX_INTERP_GAP_SEC_UA: " << MAX_INTERP_GAP_SEC_UA << "\n\n";
    paramsFile << "FHR_TOP_Y: " << std::setprecision(3) << FHR_TOP_Y << "\n";
    paramsFile << "FHR_BOTTOM_Y: " << FHR_BOTTOM_Y << "\n";
    paramsFile << "FHR_TOP_VALUE: " << FHR_TOP_VALUE << "\n";
    paramsFile << "FHR_BOTTOM_VALUE: " << FHR_BOTTOM_VALUE << "\n\n";
    paramsFile << "UA_TOP_Y: " << UA_TOP_Y << "\n";
    paramsFile << "UA_BOTTOM_Y: " << UA_BOTTOM_Y << "\n";
    paramsFile << "UA_TOP_KPA: " << UA_TOP_KPA << "\n";
    paramsFile << "UA_BOTTOM_KPA: " << UA_BOTTOM_KPA << "\n";
    paramsFile << "KPA_TO_MMHG: " << std::setprecision(6) << KPA_TO_MMHG << "\n\n";
    paramsFile << "Output ranges:\n";
    paramsFile << "  result_duration_sec: " << resultDuration << "\n";
    paramsFile << "  result_duration_min: " << resultDuration / 60.0 << "\n";
    paramsFile << "  result_rows: " << rows.size() << "\n";
    paramsFile << "  fhr_bpm: " << formatRange(fhrValues) << "\n";
    paramsFile << "  ua_kpa: " << formatRange(uaKpaValues) << "\n";
    paramsFile << "  ua_mmhg: " << formatRange(uaMmhg) << "\n";
    paramsFile << "  NaN fhr_bpm: " << countNanFhr(rows) << "\n";
    paramsFile << "  NaN ua_kpa: " << countNanUaKpa(rows) << "\n";
    paramsFile << "  NaN ua_mmhg: " << countNanUaMmhg(rows) << "\n";
}

void printCalibrationDiagnostics(
    double x0,
    double secondsPerPixel,
    const std::vector<CalibratedPoint>& fhrTrace,
    const std::vector<CalibratedPoint>& uaTrace,
    const std::vector<ResultRow>& rows
) {
    const double resultDuration = rows.empty() ? 0.0 : rows.back().timeSec - rows.front().timeSec;
    const std::vector<double> fhrValues = traceValues(fhrTrace);
    const std::vector<double> uaKpaValues = traceValues(uaTrace);
    const std::vector<double> uaMmhg = uaMmhgValues(uaTrace);

    std::cout << std::fixed;
    std::cout << "[INFO] x0: " << std::setprecision(3) << x0 << " px\n";
    std::cout << "[INFO] seconds_per_pixel: " << std::setprecision(6) << secondsPerPixel << "\n";
    std::cout << "[INFO] result duration: " << std::setprecision(2) << resultDuration
              << " sec (" << resultDuration / 60.0 << " min)\n";
    std::cout << "[INFO] fhr_bpm min/max: " << formatRange(fhrValues) << "\n";
    std::cout << "[INFO] ua_kpa min/max: " << formatRange(uaKpaValues) << "\n";
    std::cout << "[INFO] ua_mmhg min/max: " << formatRange(uaMmhg) << "\n";
    std::cout << "[INFO] result rows: " << rows.size() << "\n";
    std::cout << "[INFO] NaN fhr_bpm: " << countNanFhr(rows) << "\n";
    std::cout << "[INFO] NaN ua_kpa: " << countNanUaKpa(rows) << "\n";
    std::cout << "[INFO] NaN ua_mmhg: " << countNanUaMmhg(rows) << "\n";

    warnIfRangeOutside("fhr_bpm", fhrValues, 50.0, 210.0);
    warnIfRangeOutside("ua_kpa", uaKpaValues, -0.5, 13.0);
    warnIfManyNegativeTimes(fhrTrace, uaTrace);
}
