#pragma once

#include <opencv2/opencv.hpp>

#include <string>
#include <vector>

cv::Mat loadImage(const std::string& jpgPath, const std::string& pngPath);
cv::Mat extractRedMask(const cv::Mat& image, const std::string& debugDir);
std::vector<cv::Vec4i> detectHorizontalLines(
    const cv::Mat& mask,
    const cv::Size& fullSize,
    const std::string& debugDir
);
double computeRotationAngle(const std::vector<cv::Vec4i>& lines);
cv::Mat rotateImage(const cv::Mat& image, double angleDeg);
void drawLines(
    const cv::Mat& image,
    const std::vector<cv::Vec4i>& lines,
    const std::string& outputPath,
    const cv::Scalar& color
);
void ensureDir(const std::string& path);

// Вспомогательные данные последнего запуска Hough для логов и debug-оверлеев.
const std::vector<cv::Vec4i>& getLastRawLines();
int getLastRawLineCount();
int getLastFilteredLineCount();
