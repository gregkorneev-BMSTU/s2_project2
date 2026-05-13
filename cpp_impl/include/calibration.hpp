#pragma once

#include <string>
#include <vector>

struct TracePoint {
    double xPx = 0.0;
    double yPx = 0.0;
};

struct CalibratedPoint {
    double timeSec = 0.0;
    double value = 0.0;
};

struct ResultRow {
    int sampleIdx = 0;
    double timeSec = 0.0;
    double fhrBpm = 0.0;
    double uaKpa = 0.0;
    double uaMmhg = 0.0;
};

std::vector<TracePoint> loadTraceCsv(const std::string& path);
double computeSecondsPerPixel(double* x0Out = nullptr);
double pixelToFhr(double yPx);
double pixelToUaKpa(double yPx);
double pixelToUaMmhg(double uaKpa);
std::vector<CalibratedPoint> calibrateTrace(
    const std::vector<TracePoint>& points,
    double x0,
    double secondsPerPixel,
    double (*valueConverter)(double)
);
std::vector<ResultRow> mergeTimeSeries(
    const std::vector<CalibratedPoint>& fhrTrace,
    const std::vector<CalibratedPoint>& uaTrace
);
void saveResultCsv(const std::string& path, const std::vector<ResultRow>& rows);
void saveCalibrationParams(
    const std::string& path,
    double x0,
    double secondsPerPixel,
    const std::vector<CalibratedPoint>& fhrTrace,
    const std::vector<CalibratedPoint>& uaTrace,
    const std::vector<ResultRow>& rows
);
void printCalibrationDiagnostics(
    double x0,
    double secondsPerPixel,
    const std::vector<CalibratedPoint>& fhrTrace,
    const std::vector<CalibratedPoint>& uaTrace,
    const std::vector<ResultRow>& rows
);
