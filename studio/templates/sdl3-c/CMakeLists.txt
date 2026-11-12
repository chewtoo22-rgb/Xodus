cmake_minimum_required(VERSION 3.20)
project(__XODUS_PROJECT_NAME__ LANGUAGES C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Arch's sdl3 package installs SDL3Config.cmake with the SDL3::SDL3 target.
find_package(SDL3 REQUIRED CONFIG COMPONENTS SDL3)

add_executable(game src/main.c)
set_target_properties(game PROPERTIES OUTPUT_NAME "__XODUS_PROJECT_NAME__")
target_link_libraries(game PRIVATE SDL3::SDL3)
