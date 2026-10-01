cmake_minimum_required(VERSION 3.20)
project(linkedin_agent CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(CURL REQUIRED)
find_package(nlohmann_json 3.10 REQUIRED)

add_library(la_core
  src/http.cpp
  src/linkedin.cpp
  src/summarizer.cpp
  src/mailer.cpp
  src/report.cpp)
target_include_directories(la_core PUBLIC src)
target_link_libraries(la_core PUBLIC CURL::libcurl nlohmann_json::nlohmann_json)
target_compile_options(la_core PRIVATE -Wall -Wextra -Wpedantic)

add_executable(linkedin_agent src/main.cpp)
target_link_libraries(linkedin_agent PRIVATE la_core)

enable_testing()
add_executable(la_tests tests/tests.cpp)
target_link_libraries(la_tests PRIVATE la_core)
target_compile_definitions(la_tests PRIVATE LA_FIXTURES="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
add_test(NAME la_tests COMMAND la_tests)
