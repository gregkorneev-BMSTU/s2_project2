#pragma once

#include <opencv2/opencv.hpp>

#include <string>
#include <vector>

struct PanelSplit {
    cv::Mat upper;
    cv::Mat lower;
};

struct InterpolationResult {
    std::vector<cv::Point> points;
    std::vector<cv::Point> interpolatedPoints;
};

PanelSplit splitPanels(const cv::Mat& alignedImage);
cv::Mat extractDarkMask(const cv::Mat& panelImage);
cv::Mat cleanSignalMask(
    const cv::Mat& mask,
    const std::string& panelType,
    const std::string& cleanupMode = "soft"
);
std::vector<cv::Point> extractTracePoints(const cv::Mat& mask, const std::string& panelType);
InterpolationResult interpolateSmallGaps(const std::vector<cv::Point>& points, int maxGap);
void savePointsCsv(const std::string& outputPath, const std::vector<cv::Point>& points);
cv::Mat makeSignalOverlay(
    const cv::Mat& panelImage,
    const cv::Mat& mask,
    const std::vector<cv::Point>& tracePoints,
    const std::vector<cv::Point>& interpolatedPoints,
    const std::string& panelType,
    const std::string& cleanupMode = "soft"
);

int maxInterpolationGapForPanel(const std::string& panelType);
double traceCoveragePercent(const std::vector<cv::Point>& points, int panelWidth);
