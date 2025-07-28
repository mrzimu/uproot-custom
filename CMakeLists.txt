cmake_minimum_required(VERSION 3.20)

if(CMAKE_VERSION VERSION_GREATER_EQUAL 3.27)
    cmake_policy(SET CMP0148 NEW)
endif()

include(CMakePackageConfigHelpers)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_STANDARD 20)

project(${SKBUILD_PROJECT_NAME}
    VERSION ${SKBUILD_PROJECT_VERSION}
    LANGUAGES CXX
)

set(PYBIND11_NEWPYTHON ON)
find_package(pybind11 REQUIRED)

add_subdirectory(src/cpp)

write_basic_package_version_file(
    uproot-customConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)
configure_package_config_file(
    cmake/uproot-customConfig.cmake.in
    uproot-customConfig.cmake
    INSTALL_DESTINATION ${SKBUILD_PROJECT_NAME}/cmake/uproot-custom
)
install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/uproot-customConfigVersion.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/uproot-customConfig.cmake
    DESTINATION ${SKBUILD_PROJECT_NAME}/cmake/uproot-custom
)
