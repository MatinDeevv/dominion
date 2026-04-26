cmake_minimum_required(VERSION 3.20)
project(dominion_cpp VERSION 0.2.0 LANGUAGES CXX)

# Future pybind11 binding target:
#
# - Add a MODULE target named _dominion_cpp from cpp/src/bindings.cpp.
# - Link it against dominion_cpp, QuantLib::QuantLib, and pybind11::module.
# - Expose replay_engine and evolution_engine entry points consumed by
#   aphelion.evolution.cpp_backend.
# - Keep dominion_cpp as the standalone shared simulation library so the
#   Python extension and native harnesses share the same engine.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(QuantLib CONFIG REQUIRED)
find_package(pybind11 CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(fmt CONFIG REQUIRED)

# The restored data_ingest implementation reads Parquet directly.
find_package(Arrow CONFIG REQUIRED)
find_package(Parquet CONFIG REQUIRED)

set(DOMINION_CPP_SOURCES
    src/account.cpp
    src/data_ingest.cpp
    src/evolution_engine.cpp
    src/execution.cpp
    src/features.cpp
    src/indicator_library.cpp
    src/intelligence.cpp
    src/market_state.cpp
    src/multi_timeframe.cpp
    src/quantlib_layer.cpp
    src/regime.cpp
    src/replay_engine.cpp
    src/reporting.cpp
    src/risk_manager.cpp
    src/robustness_score.cpp
    src/robustness_validator.cpp
    src/strategy.cpp
    src/strategy_genome.cpp
    src/tournament.cpp
    src/types.cpp
    src/validation_engine.cpp
)

add_library(dominion_cpp SHARED ${DOMINION_CPP_SOURCES})

target_include_directories(dominion_cpp
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(dominion_cpp
    PUBLIC
        QuantLib::QuantLib
        fmt::fmt
        nlohmann_json::nlohmann_json
        Arrow::arrow_shared
        Parquet::parquet_shared
)

target_compile_definitions(dominion_cpp PUBLIC DOMINION_HAS_ARROW_PARQUET=1)

install(TARGETS dominion_cpp
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)
