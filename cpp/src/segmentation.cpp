#include "segmentation.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <numeric>
#include <string>
#include <vector>

namespace {

constexpr int MIN_COMPONENT_AREA = 8;
constexpr int MIN_COMPONENT_WIDTH = 2;
constexpr int MIN_COMPONENT_HEIGHT = 2;
constexpr int BORDER_CLEAN_WIDTH = 8;
constexpr int TRACE_GAP_LIMIT_UPPER = 25;
constexpr int TRACE_GAP_LIMIT_LOWER = 50;
constexpr int MAX_EDGE_ARTIFACT_WIDTH = 24;
constexpr double MIN_EDGE_ARTIFACT_HEIGHT_FRACTION = 0.45;
constexpr int MAX_JUMP_UPPER = 80;
constexpr int MAX_JUMP_LOWER = 100;
constexpr int UPPER_MAX_INTERPOLATION_GAP = 20;
constexpr int LOWER_MAX_INTERPOLATION_GAP = 45;
constexpr double LOWER_SIGNAL_Y_END_FRACTION = 0.93;
constexpr double LOWER_SIGNAL_Y_END_FRACTION_STRICT = 0.86;
constexpr double LOWER_LONG_COMPONENT_Y_FRACTION = 0.70;
constexpr double LOWER_LONG_COMPONENT_ASPECT_RATIO = 12.0;
constexpr double LOWER_LONG_COMPONENT_WIDTH_FRACTION = 0.10;
constexpr int LOWER_LONG_COMPONENT_MAX_HEIGHT = 6;
constexpr double LOWER_RIGHT_TEXT_X_FRACTION = 0.60;
constexpr double LOWER_RIGHT_TEXT_Y_FRACTION = 0.55;
constexpr int LOWER_RIGHT_TEXT_MAX_AREA = 1200;
constexpr int LOWER_RIGHT_TEXT_MAX_HEIGHT = 90;
constexpr int LOWER_RIGHT_TEXT_MAX_WIDTH = 300;
constexpr int LOWER_HORIZONTAL_KERNEL_WIDTH = 40;
constexpr int LOWER_HORIZONTAL_MIN_WIDTH = 100;
constexpr double LOWER_HORIZONTAL_MIN_ASPECT_RATIO = 12.0;
constexpr int LOWER_HORIZONTAL_MAX_HEIGHT = 6;
constexpr int LOWER_BASELINE_KEEP_MIN_HEIGHT = 10;
constexpr int LOWER_BASELINE_KEEP_MIN_AREA = 30;
constexpr double LOWER_BASELINE_Y_FRACTION = 0.70;

void ensureParentDir(const std::string& path) {
    const std::filesystem::path parent = std::filesystem::path(path).parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent);
    }
}

double getLowerRoiFraction(const std::string& cleanupMode) {
    if (cleanupMode == "strict") {
        return LOWER_SIGNAL_Y_END_FRACTION_STRICT;
    }
    return LOWER_SIGNAL_Y_END_FRACTION;
}

bool shouldRemoveUpperComponent(int maskHeight, int y, int area) {
    // Удаляем подписи и короткий шум сверху/снизу верхней панели.
    if (area < 15) {
        return true;
    }
    if (y < maskHeight * 0.08 && area < 800) {
        return true;
    }
    if (y > maskHeight * 0.92 && area < 800) {
        return true;
    }
    return false;
}

bool shouldRemoveLowerComponent(
    int maskWidth,
    int maskHeight,
    int x,
    int y,
    int width,
    int height,
    int area,
    const std::string& cleanupMode
) {
    const double aspectRatio = static_cast<double>(width) / std::max(1, height);

    if (area < 20) {
        return true;
    }

    const bool isLowerLongLine =
        y > maskHeight * LOWER_LONG_COMPONENT_Y_FRACTION &&
        aspectRatio > LOWER_LONG_COMPONENT_ASPECT_RATIO &&
        height <= LOWER_LONG_COMPONENT_MAX_HEIGHT &&
        width > maskWidth * LOWER_LONG_COMPONENT_WIDTH_FRACTION;

    const bool isRightLowerText =
        x > maskWidth * LOWER_RIGHT_TEXT_X_FRACTION &&
        y > maskHeight * LOWER_RIGHT_TEXT_Y_FRACTION &&
        area < LOWER_RIGHT_TEXT_MAX_AREA &&
        height < LOWER_RIGHT_TEXT_MAX_HEIGHT &&
        width < LOWER_RIGHT_TEXT_MAX_WIDTH;

    if (isLowerLongLine || isRightLowerText) {
        return true;
    }

    const bool isLowSignalLike =
        y > maskHeight * LOWER_BASELINE_Y_FRACTION &&
        height >= LOWER_BASELINE_KEEP_MIN_HEIGHT &&
        area >= LOWER_BASELINE_KEEP_MIN_AREA;

    if (cleanupMode == "soft" && isLowSignalLike) {
        return false;
    }

    return false;
}

bool shouldRemoveComponent(
    const std::string& panelType,
    int maskWidth,
    int maskHeight,
    int x,
    int y,
    int width,
    int height,
    int area,
    const std::string& cleanupMode
) {
    const double aspectRatio = static_cast<double>(width) / std::max(1, height);

    if (area < MIN_COMPONENT_AREA) {
        return true;
    }
    if (width < MIN_COMPONENT_WIDTH || height < MIN_COMPONENT_HEIGHT) {
        return true;
    }
    if (area < 40 && width < 10 && height < 10) {
        return true;
    }
    if (aspectRatio > 15.0 && height < 5) {
        return true;
    }
    if (
        x + width >= maskWidth - BORDER_CLEAN_WIDTH &&
        width <= MAX_EDGE_ARTIFACT_WIDTH &&
        height >= maskHeight * MIN_EDGE_ARTIFACT_HEIGHT_FRACTION
    ) {
        return true;
    }

    if (panelType == "upper") {
        return shouldRemoveUpperComponent(maskHeight, y, area);
    }

    return shouldRemoveLowerComponent(
        maskWidth,
        maskHeight,
        x,
        y,
        width,
        height,
        area,
        cleanupMode
    );
}

cv::Mat filterSignalComponents(
    const cv::Mat& mask,
    const std::string& panelType,
    const std::string& cleanupMode,
    cv::Mat* removedOut = nullptr
) {
    cv::Mat labels;
    cv::Mat stats;
    cv::Mat centroids;
    const int componentCount = cv::connectedComponentsWithStats(mask, labels, stats, centroids, 8);

    cv::Mat filtered = cv::Mat::zeros(mask.size(), mask.type());
    cv::Mat removed = cv::Mat::zeros(mask.size(), mask.type());
    const int maskHeight = mask.rows;
    const int maskWidth = mask.cols;

    for (int componentId = 1; componentId < componentCount; ++componentId) {
        const int x = stats.at<int>(componentId, cv::CC_STAT_LEFT);
        const int y = stats.at<int>(componentId, cv::CC_STAT_TOP);
        const int width = stats.at<int>(componentId, cv::CC_STAT_WIDTH);
        const int height = stats.at<int>(componentId, cv::CC_STAT_HEIGHT);
        const int area = stats.at<int>(componentId, cv::CC_STAT_AREA);

        cv::Mat componentMask = labels == componentId;
        if (shouldRemoveComponent(panelType, maskWidth, maskHeight, x, y, width, height, area, cleanupMode)) {
            removed.setTo(255, componentMask);
        } else {
            filtered.setTo(255, componentMask);
        }
    }

    if (removedOut != nullptr) {
        *removedOut = removed;
    }
    return filtered;
}

cv::Mat removeLowerHorizontalArtifacts(
    const cv::Mat& mask,
    const std::string& panelType,
    const std::string& cleanupMode,
    cv::Mat* removedOut = nullptr
) {
    (void)cleanupMode;

    cv::Mat removed = cv::Mat::zeros(mask.size(), mask.type());
    if (panelType != "lower") {
        if (removedOut != nullptr) {
            *removedOut = removed;
        }
        return mask.clone();
    }

    cv::Mat horizontalKernel = cv::getStructuringElement(
        cv::MORPH_RECT,
        cv::Size(LOWER_HORIZONTAL_KERNEL_WIDTH, 3)
    );
    cv::Mat horizontalMask;
    cv::morphologyEx(mask, horizontalMask, cv::MORPH_OPEN, horizontalKernel);
    horizontalMask.rowRange(0, static_cast<int>(mask.rows * LOWER_LONG_COMPONENT_Y_FRACTION)).setTo(0);

    cv::Mat labels;
    cv::Mat stats;
    cv::Mat centroids;
    const int componentCount = cv::connectedComponentsWithStats(horizontalMask, labels, stats, centroids, 8);

    for (int componentId = 1; componentId < componentCount; ++componentId) {
        const int width = stats.at<int>(componentId, cv::CC_STAT_WIDTH);
        const int height = stats.at<int>(componentId, cv::CC_STAT_HEIGHT);
        const double aspectRatio = static_cast<double>(width) / std::max(1, height);

        if (
            width >= LOWER_HORIZONTAL_MIN_WIDTH &&
            aspectRatio >= LOWER_HORIZONTAL_MIN_ASPECT_RATIO &&
            height <= LOWER_HORIZONTAL_MAX_HEIGHT
        ) {
            removed.setTo(255, labels == componentId);
        }
    }

    cv::Mat cleaned = mask.clone();
    cleaned.setTo(0, removed > 0);

    if (removedOut != nullptr) {
        *removedOut = removed;
    }
    return cleaned;
}

int medianY(const std::vector<int>& values) {
    if (values.empty()) {
        return 0;
    }

    std::vector<int> sorted = values;
    std::sort(sorted.begin(), sorted.end());
    const size_t middle = sorted.size() / 2;
    if (sorted.size() % 2 == 1) {
        return sorted[middle];
    }
    return static_cast<int>(std::llround((sorted[middle - 1] + sorted[middle]) / 2.0));
}

void drawLabel(cv::Mat& image, int x, int y, const std::string& text, const cv::Scalar& color) {
    const int font = cv::FONT_HERSHEY_SIMPLEX;
    const double scale = 0.65;
    const int thickness = 2;
    int baseline = 0;
    const cv::Size textSize = cv::getTextSize(text, font, scale, thickness, &baseline);

    x = std::max(0, std::min(image.cols - textSize.width - 12, x));
    y = std::max(textSize.height + 8, std::min(image.rows - 8, y));

    cv::rectangle(
        image,
        cv::Point(x - 4, y - textSize.height - 8),
        cv::Point(x + textSize.width + 8, y + 6),
        cv::Scalar(255, 255, 255),
        cv::FILLED
    );
    cv::putText(image, text, cv::Point(x, y), font, scale, color, thickness, cv::LINE_AA);
}

}  // namespace

PanelSplit splitPanels(const cv::Mat& alignedImage) {
    const int height = alignedImage.rows;

    const int upperStart = static_cast<int>(height * 0.05);
    const int upperEnd = static_cast<int>(height * 0.60);
    const int lowerStart = static_cast<int>(height * 0.62);
    const int lowerEnd = static_cast<int>(height * 0.98);

    PanelSplit split;
    split.upper = alignedImage.rowRange(upperStart, upperEnd).clone();
    split.lower = alignedImage.rowRange(lowerStart, lowerEnd).clone();
    return split;
}

cv::Mat extractDarkMask(const cv::Mat& panelImage) {
    cv::Mat gray;
    cv::Mat blurred;
    cv::Mat rawMask;

    cv::cvtColor(panelImage, gray, cv::COLOR_BGR2GRAY);
    cv::GaussianBlur(gray, blurred, cv::Size(5, 5), 0);
    cv::threshold(blurred, rawMask, 160, 255, cv::THRESH_BINARY_INV);
    return rawMask;
}

cv::Mat cleanSignalMask(
    const cv::Mat& mask,
    const std::string& panelType,
    const std::string& cleanupMode
) {
    cv::Mat clean = mask.clone();

    // Убираем темные полосы по краям фотографии.
    clean.colRange(0, std::min(BORDER_CLEAN_WIDTH, clean.cols)).setTo(0);
    clean.colRange(std::max(0, clean.cols - BORDER_CLEAN_WIDTH), clean.cols).setTo(0);
    clean.rowRange(0, std::min(BORDER_CLEAN_WIDTH, clean.rows)).setTo(0);
    clean.rowRange(std::max(0, clean.rows - BORDER_CLEAN_WIDTH), clean.rows).setTo(0);

    cv::Mat openKernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(2, 2));
    cv::morphologyEx(clean, clean, cv::MORPH_OPEN, openKernel);

    if (panelType == "lower") {
        const int roiYEnd = static_cast<int>(clean.rows * getLowerRoiFraction(cleanupMode));
        clean.rowRange(roiYEnd, clean.rows).setTo(0);
    }

    cv::Mat filtered = filterSignalComponents(clean, panelType, cleanupMode);

    cv::Mat closeKernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(2, 3));
    cv::morphologyEx(filtered, filtered, cv::MORPH_CLOSE, closeKernel);

    filtered = removeLowerHorizontalArtifacts(filtered, panelType, cleanupMode);
    filtered = filterSignalComponents(filtered, panelType, cleanupMode);

    return filtered;
}

std::vector<cv::Point> extractTracePoints(const cv::Mat& mask, const std::string& panelType) {
    std::vector<cv::Point> points;
    int previousY = -1;
    const int maxJump = panelType == "upper" ? MAX_JUMP_UPPER : MAX_JUMP_LOWER;

    for (int x = 0; x < mask.cols; ++x) {
        std::vector<int> ys;
        ys.reserve(mask.rows / 4);

        for (int y = 0; y < mask.rows; ++y) {
            if (mask.at<uchar>(y, x) > 0) {
                ys.push_back(y);
            }
        }

        if (ys.empty()) {
            previousY = -1;
            continue;
        }

        int y = 0;
        if (previousY < 0) {
            y = medianY(ys);
        } else {
            auto closest = std::min_element(
                ys.begin(),
                ys.end(),
                [previousY](int a, int b) {
                    return std::abs(a - previousY) < std::abs(b - previousY);
                }
            );
            y = *closest;

            const bool isLowerBaselineCandidate =
                panelType == "lower" && y > mask.rows * LOWER_BASELINE_Y_FRACTION;

            if (std::abs(y - previousY) > maxJump && !isLowerBaselineCandidate) {
                previousY = -1;
                continue;
            }
        }

        points.emplace_back(x, y);
        previousY = y;
    }

    return points;
}

InterpolationResult interpolateSmallGaps(const std::vector<cv::Point>& points, int maxGap) {
    InterpolationResult result;

    if (points.size() < 2) {
        result.points = points;
        return result;
    }

    result.points.push_back(points.front());

    for (size_t index = 1; index < points.size(); ++index) {
        const cv::Point previous = result.points.back();
        const cv::Point current = points[index];
        const int gap = current.x - previous.x;

        if (gap > 1 && gap <= maxGap) {
            for (int offset = 1; offset < gap; ++offset) {
                const double ratio = static_cast<double>(offset) / gap;
                const int filledY = static_cast<int>(std::llround(previous.y + (current.y - previous.y) * ratio));
                const cv::Point filled(previous.x + offset, filledY);
                result.points.push_back(filled);
                result.interpolatedPoints.push_back(filled);
            }
        }

        result.points.push_back(current);
    }

    return result;
}

void savePointsCsv(const std::string& outputPath, const std::vector<cv::Point>& points) {
    ensureParentDir(outputPath);
    std::ofstream csvFile(outputPath);
    csvFile << "x_px,y_px\n";
    for (const cv::Point& point : points) {
        csvFile << point.x << "," << point.y << "\n";
    }
}

cv::Mat makeSignalOverlay(
    const cv::Mat& panelImage,
    const cv::Mat& mask,
    const std::vector<cv::Point>& tracePoints,
    const std::vector<cv::Point>& interpolatedPoints,
    const std::string& panelType,
    const std::string& cleanupMode
) {
    cv::Mat overlay = panelImage.clone();
    cv::Mat green(panelImage.size(), panelImage.type(), cv::Scalar(0, 255, 0));
    cv::Mat blended;
    cv::addWeighted(overlay, 0.35, green, 0.65, 0.0, blended);
    blended.copyTo(overlay, mask > 0);

    const int traceGapLimit = panelType == "upper" ? TRACE_GAP_LIMIT_UPPER : TRACE_GAP_LIMIT_LOWER;
    for (size_t index = 1; index < tracePoints.size(); ++index) {
        const cv::Point previous = tracePoints[index - 1];
        const cv::Point current = tracePoints[index];
        if (current.x - previous.x <= traceGapLimit) {
            cv::line(overlay, previous, current, cv::Scalar(0, 0, 255), 2, cv::LINE_AA);
        }
    }

    for (const cv::Point& point : interpolatedPoints) {
        cv::circle(overlay, point, 2, cv::Scalar(0, 255, 255), cv::FILLED, cv::LINE_AA);
    }

    if (panelType == "lower") {
        const int roiYEnd = static_cast<int>(panelImage.rows * getLowerRoiFraction(cleanupMode));
        cv::line(
            overlay,
            cv::Point(0, roiYEnd),
            cv::Point(panelImage.cols - 1, roiYEnd),
            cv::Scalar(255, 0, 0),
            2,
            cv::LINE_AA
        );
        drawLabel(overlay, 14, roiYEnd - 8, "lower ROI", cv::Scalar(255, 0, 0));
    }

    return overlay;
}

int maxInterpolationGapForPanel(const std::string& panelType) {
    return panelType == "upper" ? UPPER_MAX_INTERPOLATION_GAP : LOWER_MAX_INTERPOLATION_GAP;
}

double traceCoveragePercent(const std::vector<cv::Point>& points, int panelWidth) {
    return 100.0 * static_cast<double>(points.size()) / std::max(1, panelWidth);
}
