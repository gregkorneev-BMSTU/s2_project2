#include "calibration.hpp"
#include "preprocess.hpp"
#include "segmentation.hpp"

#include <opencv2/opencv.hpp>

#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>

int main() {
    // Запуск по ТЗ идет из cpp, поэтому поддерживаем и корень проекта, и текущую папку.
    const std::string projectRoot = std::filesystem::exists("data") ? "." : "..";
    const std::string resultsDir = projectRoot + "/results/cpp";
    const std::string debugDir = resultsDir + "/debug";
    const std::string jpgPath = projectRoot + "/data/input.jpg";
    const std::string pngPath = projectRoot + "/data/input.png";

    ensureDir(resultsDir);
    ensureDir(debugDir);

    cv::Mat image = loadImage(jpgPath, pngPath);
    if (image.empty()) {
        std::cerr << "[WARN] Не удалось загрузить изображение: data/input.jpg или data/input.png\n";
        return 1;
    }

    std::cout << "[INFO] Размер изображения: " << image.cols << "x" << image.rows << "\n";
    cv::imwrite(resultsDir + "/original.png", image);

    cv::Mat redMask = extractRedMask(image, debugDir);
    std::vector<cv::Vec4i> horizontalLines = detectHorizontalLines(redMask, image.size(), debugDir);
    double angle = computeRotationAngle(horizontalLines);

    cv::Mat aligned = rotateImage(image, -angle);
    cv::imwrite(resultsDir + "/aligned.png", aligned);

    PanelSplit panels = splitPanels(aligned);
    cv::imwrite(resultsDir + "/upper_panel.png", panels.upper);
    cv::imwrite(resultsDir + "/lower_panel.png", panels.lower);

    auto analyzePanel = [&](const cv::Mat& panel, const std::string& panelType) {
        const std::string prefix = panelType == "upper" ? "upper" : "lower";
        const std::string title = panelType == "upper" ? "Upper" : "Lower";

        cv::Mat rawMask = extractDarkMask(panel);
        cv::Mat cleanMask = cleanSignalMask(rawMask, panelType, "soft");
        std::vector<cv::Point> rawPoints = extractTracePoints(cleanMask, panelType);
        InterpolationResult interpolation = interpolateSmallGaps(
            rawPoints,
            maxInterpolationGapForPanel(panelType)
        );
        cv::Mat overlay = makeSignalOverlay(
            panel,
            cleanMask,
            interpolation.points,
            interpolation.interpolatedPoints,
            panelType,
            "soft"
        );

        cv::imwrite(debugDir + "/" + prefix + "_clean_mask.png", cleanMask);
        cv::imwrite(debugDir + "/" + prefix + "_signal_overlay.png", overlay);
        savePointsCsv(debugDir + "/" + prefix + "_points.csv", interpolation.points);

        const int whitePixels = cv::countNonZero(cleanMask);
        const double coverage = traceCoveragePercent(interpolation.points, panel.cols);

        std::cout << "[INFO] " << title << " panel size: " << panel.cols << "x" << panel.rows << "\n";
        std::cout << "[INFO] " << prefix << "_clean_mask white pixels: " << whitePixels << "\n";
        std::cout << "[INFO] " << title << " extracted points: " << interpolation.points.size() << "\n";
        std::cout << "[INFO] " << title << " coverage: " << coverage << "%\n";
    };

    analyzePanel(panels.upper, "upper");
    analyzePanel(panels.lower, "lower");

    double x0 = 0.0;
    const double secondsPerPixel = computeSecondsPerPixel(&x0);
    const std::vector<TracePoint> upperPoints = loadTraceCsv(debugDir + "/upper_points.csv");
    const std::vector<TracePoint> lowerPoints = loadTraceCsv(debugDir + "/lower_points.csv");
    const std::vector<CalibratedPoint> fhrTrace =
        calibrateTrace(upperPoints, x0, secondsPerPixel, pixelToFhr);
    const std::vector<CalibratedPoint> uaTrace =
        calibrateTrace(lowerPoints, x0, secondsPerPixel, pixelToUaKpa);
    const std::vector<ResultRow> resultRows = mergeTimeSeries(fhrTrace, uaTrace);

    saveResultCsv(resultsDir + "/result.csv", resultRows);
    printCalibrationDiagnostics(x0, secondsPerPixel, fhrTrace, uaTrace, resultRows);
    saveCalibrationParams(
        resultsDir + "/calibration_params.txt",
        x0,
        secondsPerPixel,
        fhrTrace,
        uaTrace,
        resultRows
    );

    drawLines(image, getLastRawLines(), debugDir + "/hough_lines_all.png", cv::Scalar(0, 255, 0));
    cv::Mat rawOverlay = cv::imread(debugDir + "/hough_lines_all.png", cv::IMREAD_COLOR);
    if (rawOverlay.empty()) {
        rawOverlay = image;
    }
    drawLines(rawOverlay, horizontalLines, debugDir + "/hough_lines_filtered.png", cv::Scalar(0, 0, 255));

    std::ofstream rotationFile(debugDir + "/rotation.txt");
    rotationFile << std::fixed << std::setprecision(4);
    rotationFile << "angle: " << angle << " degrees\n";
    rotationFile << "raw_lines: " << getLastRawLineCount() << "\n";
    rotationFile << "filtered_lines: " << getLastFilteredLineCount() << "\n";

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "[INFO] Итоговый угол: " << angle << " градусов\n";
    std::cout << "[INFO] Этап 1 C++ завершён\n";
    std::cout << "[INFO] Этап 2 C++ segmentation/extraction завершён\n";
    std::cout << "[INFO] C++ calibration completed\n";
    std::cout << "[INFO] result.csv generated\n";
    std::cout << "[INFO] Physical time series built\n";
    std::cout << "[INFO] Угол поворота: " << angle << " градусов\n";
    std::cout << "[INFO] Файлы сохранены в results/cpp/\n";

    return 0;
}
