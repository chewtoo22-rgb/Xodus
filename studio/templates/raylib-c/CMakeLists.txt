cmake_minimum_required(VERSION 3.20)
project(__XODUS_PROJECT_NAME__ LANGUAGES C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Arch's raylib package ships a CMake config; fall back to pkg-config so the
# template keeps building if the config file layout changes.
find_package(raylib CONFIG QUIET)
if(NOT TARGET raylib)
  find_package(PkgConfig REQUIRED)
  pkg_check_modules(RAYLIB REQUIRED IMPORTED_TARGET raylib)
endif()

add_executable(game src/main.c)
set_target_properties(game PROPERTIES OUTPUT_NAME "__XODUS_PROJECT_NAME__")
if(TARGET raylib)
  target_link_libraries(game PRIVATE raylib m)
else()
  target_link_libraries(game PRIVATE PkgConfig::RAYLIB m)
endif()
