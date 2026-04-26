# Future pybind11 binding target:
#
# - Add pybind11 via vcpkg/CMake once the C++ simulation engine is restored here.
# - Build a Python extension named _dominion_cpp from cpp/src/bindings.cpp.
# - Expose replay_engine and evolution_engine functions for
#   aphelion.evolution.cpp_backend.
# - Link the extension against QuantLib and the standalone simulation sources.

cmake_minimum_required(VERSION 3.20)
project(dominion_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

