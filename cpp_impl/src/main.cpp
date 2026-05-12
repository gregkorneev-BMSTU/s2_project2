#include "preprocess.hpp"

#include <opencv2/opencv.hpp>

#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>

int main() {
    // Запуск по ТЗ идет из cpp_impl, поэтому поддерживаем и корень проекта, и текущую папку.
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
    std::cout << "[INFO] Угол поворота: " << angle << " градусов\n";
    std::cout << "[INFO] Файлы сохранены в results/cpp/\n";

    return 0;
}
