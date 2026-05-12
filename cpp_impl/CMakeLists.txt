cmake_minimum_required(VERSION 3.12)

project(cpp_medical_digitizer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(OpenCV REQUIRED)

add_executable(cpp_medical_digitizer
    src/main.cpp
    src/preprocess.cpp
)

target_include_directories(cpp_medical_digitizer PRIVATE
    include
    ${OpenCV_INCLUDE_DIRS}
)

target_link_libraries(cpp_medical_digitizer PRIVATE ${OpenCV_LIBS})
