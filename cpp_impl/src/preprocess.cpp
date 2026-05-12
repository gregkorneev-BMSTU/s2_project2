#include "preprocess.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>

namespace {

constexpr int DELTA_RG = 8;
constexpr int DELTA_RB = 8;
constexpr int A_THRESHOLD = 140;
constexpr int MORPH_SIZE = 3;
constexpr int DILATE_ITERATIONS = 2;
constexpr int OPEN_ITERATIONS = 1;
constexpr int HORIZONTAL_KERNEL_WIDTH = 25;
constexpr double SEARCH_Y_START = 0.08;
constexpr double SEARCH_Y_END = 0.95;
constexpr int CANNY_LOW = 50;
constexpr int CANNY_HIGH = 150;
constexpr int HOUGH_THRESHOLD = 30;
constexpr double HOUGH_MIN_LINE_FRAC = 0.15;
constexpr int HOUGH_MAX_LINE_GAP = 40;
constexpr double ANGLE_THRESHOLD = 15.0;
constexpr int MIN_FILTERED_LINES_WARNING = 5;

std::vector<cv::Vec4i> g_lastRawLines;
std::vector<cv::Vec4i> g_lastFilteredLines;

void saveImage(const std::string& path, const cv::Mat& image) {
    ensureDir(std::filesystem::path(path).parent_path().string());
    cv::imwrite(path, image);
}

int countPixels(const cv::Mat& mask) {
    return cv::countNonZero(mask);
}

void printMaskPixels(const std::string& name, const cv::Mat& mask) {
    std::cout << "[INFO] " << name << " pixels: " << countPixels(mask) << "\n";
}

cv::Mat buildRedLikeMask(const cv::Mat& image) {
    std::vector<cv::Mat> channels;
    cv::split(image, channels);

    cv::Mat blue16;
    cv::Mat green16;
    cv::Mat red16;
    channels[0].convertTo(blue16, CV_16S);
    channels[1].convertTo(green16, CV_16S);
    channels[2].convertTo(red16, CV_16S);

    cv::Mat redGtGreen;
    cv::Mat redGtBlue;
    cv::compare(red16, green16 + DELTA_RG, redGtGreen, cv::CMP_GT);
    cv::compare(red16, blue16 + DELTA_RB, redGtBlue, cv::CMP_GT);

    cv::Mat redLikeMask;
    cv::bitwise_and(redGtGreen, redGtBlue, redLikeMask);
    return redLikeMask;
}

void buildLabRedMask(const cv::Mat& image, cv::Mat& labAChannel, cv::Mat& redFromLabMask) {
    cv::Mat labImage;
    cv::cvtColor(image, labImage, cv::COLOR_BGR2Lab);

    std::vector<cv::Mat> labChannels;
    cv::split(labImage, labChannels);
    cv::normalize(labChannels[1], labAChannel, 0, 255, cv::NORM_MINMAX);
    cv::threshold(labAChannel, redFromLabMask, A_THRESHOLD, 255, cv::THRESH_BINARY);
}

double normalizeLineAngle(double angleDeg) {
    // Приведение к диапазону около горизонтали по правилам ТЗ.
    if (angleDeg > 45.0) {
        angleDeg -= 90.0;
    }
    if (angleDeg < -45.0) {
        angleDeg += 90.0;
    }
    return angleDeg;
}

double lineAngle(const cv::Vec4i& line) {
    const double dx = static_cast<double>(line[2] - line[0]);
    const double dy = static_cast<double>(line[3] - line[1]);
    return normalizeLineAngle(std::atan2(dy, dx) * 180.0 / CV_PI);
}

double lineLength(const cv::Vec4i& line) {
    const double dx = static_cast<double>(line[2] - line[0]);
    const double dy = static_cast<double>(line[3] - line[1]);
    return std::sqrt(dx * dx + dy * dy);
}

std::vector<cv::Vec4i> runHough(const cv::Mat& binaryImage) {
    std::vector<cv::Vec4i> lines;
    const int minLineLength = std::max(30, static_cast<int>(binaryImage.cols * HOUGH_MIN_LINE_FRAC));
    cv::HoughLinesP(
        binaryImage,
        lines,
        1,
        CV_PI / 180.0,
        HOUGH_THRESHOLD,
        minLineLength,
        HOUGH_MAX_LINE_GAP
    );
    return lines;
}

std::vector<cv::Vec4i> filterHorizontalLines(const std::vector<cv::Vec4i>& lines, int imageWidth) {
    std::vector<cv::Vec4i> filtered;
    const double minLength = imageWidth * HOUGH_MIN_LINE_FRAC;

    for (const cv::Vec4i& line : lines) {
        const double angle = lineAngle(line);
        const double length = lineLength(line);

        if (std::abs(angle) < ANGLE_THRESHOLD && length > minLength) {
            filtered.push_back(line);
        }
    }

    return filtered;
}

double median(std::vector<double> values) {
    if (values.empty()) {
        return 0.0;
    }

    std::sort(values.begin(), values.end());
    const size_t middle = values.size() / 2;
    if (values.size() % 2 == 1) {
        return values[middle];
    }
    return (values[middle - 1] + values[middle]) / 2.0;
}

}  // namespace

void ensureDir(const std::string& path) {
    if (!path.empty()) {
        std::filesystem::create_directories(path);
    }
}

cv::Mat loadImage(const std::string& jpgPath, const std::string& pngPath) {
    if (std::filesystem::exists(jpgPath)) {
        cv::Mat image = cv::imread(jpgPath, cv::IMREAD_COLOR);
        if (!image.empty()) {
            return image;
        }
    }

    std::cout << "[WARN] Файл " << jpgPath << " не найден, используется " << pngPath << "\n";
    return cv::imread(pngPath, cv::IMREAD_COLOR);
}

cv::Mat extractRedMask(const cv::Mat& image, const std::string& debugDir) {
    cv::Mat hsvImage;
    cv::cvtColor(image, hsvImage, cv::COLOR_BGR2HSV);

    cv::Mat redMask1;
    cv::Mat redMask2;
    cv::inRange(hsvImage, cv::Scalar(0, 10, 120), cv::Scalar(20, 255, 255), redMask1);
    cv::inRange(hsvImage, cv::Scalar(160, 10, 120), cv::Scalar(180, 255, 255), redMask2);

    cv::Mat hsvRedMask;
    cv::bitwise_or(redMask1, redMask2, hsvRedMask);

    cv::Mat redLikeMask = buildRedLikeMask(image);

    cv::Mat labAChannel;
    cv::Mat redFromLabMask;
    buildLabRedMask(image, labAChannel, redFromLabMask);

    cv::Mat redMaskCombined;
    cv::bitwise_or(hsvRedMask, redLikeMask, redMaskCombined);
    cv::bitwise_or(redMaskCombined, redFromLabMask, redMaskCombined);

    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(MORPH_SIZE, MORPH_SIZE));

    cv::Mat redMaskAfterClose;
    cv::Mat redMaskAfterDilate;
    cv::Mat redMaskClean;
    cv::morphologyEx(redMaskCombined, redMaskAfterClose, cv::MORPH_CLOSE, kernel);
    cv::dilate(redMaskAfterClose, redMaskAfterDilate, kernel, cv::Point(-1, -1), DILATE_ITERATIONS);
    cv::morphologyEx(
        redMaskAfterDilate,
        redMaskClean,
        cv::MORPH_OPEN,
        kernel,
        cv::Point(-1, -1),
        OPEN_ITERATIONS
    );

    saveImage(debugDir + "/red_mask_1.png", redMask1);
    saveImage(debugDir + "/red_mask_2.png", redMask2);
    saveImage(debugDir + "/red_like_mask.png", redLikeMask);
    saveImage(debugDir + "/lab_a_channel.png", labAChannel);
    saveImage(debugDir + "/red_from_lab_mask.png", redFromLabMask);
    saveImage(debugDir + "/red_mask_combined_before_morph.png", redMaskCombined);
    saveImage(debugDir + "/red_mask_after_close.png", redMaskAfterClose);
    saveImage(debugDir + "/red_mask_after_dilate.png", redMaskAfterDilate);
    saveImage(debugDir + "/red_mask_clean.png", redMaskClean);

    printMaskPixels("red_mask_1", redMask1);
    printMaskPixels("red_mask_2", redMask2);
    printMaskPixels("red_like_mask", redLikeMask);
    printMaskPixels("lab_red_mask", redFromLabMask);
    printMaskPixels("red_mask_clean", redMaskClean);

    return redMaskClean;
}

std::vector<cv::Vec4i> detectHorizontalLines(
    const cv::Mat& mask,
    const cv::Size& fullSize,
    const std::string& debugDir
) {
    const int yStart = static_cast<int>(fullSize.height * SEARCH_Y_START);
    const int yEnd = static_cast<int>(fullSize.height * SEARCH_Y_END);

    cv::Mat searchRoiMask = cv::Mat::zeros(mask.size(), mask.type());
    mask.rowRange(yStart, yEnd).copyTo(searchRoiMask.rowRange(yStart, yEnd));
    saveImage(debugDir + "/search_roi_mask.png", searchRoiMask);

    const int roiHeight = yEnd - yStart;
    std::cout << "[INFO] Search ROI: y=" << yStart << ":" << yEnd
              << " (" << fullSize.width << "x" << roiHeight << ")\n";

    cv::Mat kernelHorizontal = cv::getStructuringElement(
        cv::MORPH_RECT,
        cv::Size(HORIZONTAL_KERNEL_WIDTH, 1)
    );
    cv::Mat horizontalEmphasisMask;
    cv::morphologyEx(searchRoiMask, horizontalEmphasisMask, cv::MORPH_OPEN, kernelHorizontal);
    saveImage(debugDir + "/horizontal_emphasis_mask.png", horizontalEmphasisMask);
    saveImage(debugDir + "/hough_input_mask.png", horizontalEmphasisMask);

    printMaskPixels("horizontal emphasis mask", horizontalEmphasisMask);

    std::vector<cv::Vec4i> maskRawLines = runHough(horizontalEmphasisMask);
    std::vector<cv::Vec4i> maskFilteredLines = filterHorizontalLines(maskRawLines, fullSize.width);

    cv::Mat blurredMask;
    cv::Mat edges;
    cv::GaussianBlur(searchRoiMask, blurredMask, cv::Size(5, 5), 0);
    cv::Canny(blurredMask, edges, CANNY_LOW, CANNY_HIGH);
    saveImage(debugDir + "/edges.png", edges);

    g_lastRawLines = maskRawLines;
    g_lastFilteredLines = maskFilteredLines;

    if (static_cast<int>(maskFilteredLines.size()) < MIN_FILTERED_LINES_WARNING) {
        std::cout << "[WARN] Hough по mask не дал линий, используется fallback edges\n";
        g_lastRawLines = runHough(edges);
        g_lastFilteredLines = filterHorizontalLines(g_lastRawLines, fullSize.width);
    }

    std::cout << "[INFO] Hough raw lines: " << g_lastRawLines.size() << "\n";
    std::cout << "[INFO] Hough filtered horizontal lines: " << g_lastFilteredLines.size() << "\n";

    return g_lastFilteredLines;
}

double computeRotationAngle(const std::vector<cv::Vec4i>& lines) {
    if (lines.empty()) {
        std::cout << "[WARN] Горизонтальные линии не найдены, используется угол 0 градусов\n";
        return 0.0;
    }

    std::vector<double> angles;
    angles.reserve(lines.size());
    for (const cv::Vec4i& line : lines) {
        angles.push_back(lineAngle(line));
    }

    const double firstMedian = median(angles);
    std::vector<double> trimmedAngles;
    for (double angle : angles) {
        if (angle >= firstMedian - 5.0 && angle <= firstMedian + 5.0) {
            trimmedAngles.push_back(angle);
        }
    }

    if (trimmedAngles.empty()) {
        return firstMedian;
    }

    return median(trimmedAngles);
}

cv::Mat rotateImage(const cv::Mat& image, double angleDeg) {
    const cv::Point2f center(
        static_cast<float>(image.cols) / 2.0f,
        static_cast<float>(image.rows) / 2.0f
    );
    cv::Mat rotationMatrix = cv::getRotationMatrix2D(center, angleDeg, 1.0);

    cv::Mat rotated;
    cv::warpAffine(
        image,
        rotated,
        rotationMatrix,
        image.size(),
        cv::INTER_LINEAR,
        cv::BORDER_REPLICATE
    );
    return rotated;
}

void drawLines(
    const cv::Mat& image,
    const std::vector<cv::Vec4i>& lines,
    const std::string& outputPath,
    const cv::Scalar& color
) {
    cv::Mat debugImage;
    if (image.channels() == 1) {
        cv::cvtColor(image, debugImage, cv::COLOR_GRAY2BGR);
    } else {
        debugImage = image.clone();
    }

    for (const cv::Vec4i& line : lines) {
        cv::line(
            debugImage,
            cv::Point(line[0], line[1]),
            cv::Point(line[2], line[3]),
            color,
            2,
            cv::LINE_AA
        );
    }

    saveImage(outputPath, debugImage);
}

const std::vector<cv::Vec4i>& getLastRawLines() {
    return g_lastRawLines;
}

int getLastRawLineCount() {
    return static_cast<int>(g_lastRawLines.size());
}

int getLastFilteredLineCount() {
    return static_cast<int>(g_lastFilteredLines.size());
}
