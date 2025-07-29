cmake_minimum_required(VERSION 3.20)

if(CMAKE_VERSION VERSION_GREATER_EQUAL 3.27)
    cmake_policy(SET CMP0148 NEW)
endif()

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(PYBIND11_NEWPYTHON ON)

project(${SKBUILD_PROJECT_NAME}
    VERSION ${SKBUILD_PROJECT_VERSION}
    LANGUAGES CXX
)

find_package(pybind11 REQUIRED)

# Add the uproot-custom module

pybind11_add_module(_cpp
    src/uproot-custom.cc
)

target_include_directories(_cpp
    PRIVATE $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

# Install targets and configuration files
if(DEFINED SKBUILD_PROJECT_NAME)
    include(CMakePackageConfigHelpers)
    write_basic_package_version_file(
        uproot-customConfigVersion.cmake
        VERSION ${PROJECT_VERSION}
        COMPATIBILITY SameMajorVersion
    )

    install(
        TARGETS _cpp
        LIBRARY DESTINATION ${SKBUILD_PROJECT_NAME}
    )

    install( # header files
        DIRECTORY ${CMAKE_CURRENT_LIST_DIR}/include
        DESTINATION ${SKBUILD_PROJECT_NAME}
    )

    install( # CMake configuration files
        FILES
            ${CMAKE_CURRENT_LIST_DIR}/share/cmake/uproot-customConfig.cmake
            ${CMAKE_CURRENT_BINARY_DIR}/uproot-customConfigVersion.cmake
        DESTINATION ${SKBUILD_PROJECT_NAME}/share/cmake/
    )
endif()