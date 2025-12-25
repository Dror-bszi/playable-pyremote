cmake_minimum_required(VERSION 3.0)
project(detect_controller)

set(CMAKE_CXX_STANDARD 20)

find_package(SDL2 REQUIRED)

add_executable(detect_controller main.cpp)

target_link_libraries(detect_controller PRIVATE
        SDL2::SDL2
        SDL2::SDL2main
)
