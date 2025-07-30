cmake_minimum_required(VERSION 3.20)

if(CMAKE_VERSION VERSION_GREATER_EQUAL 3.27)
    cmake_policy(SET CMP0148 NEW)
endif()

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_STANDARD 20)

project(${SKBUILD_PROJECT_NAME}
    VERSION ${SKBUILD_PROJECT_VERSION}
    LANGUAGES CXX
)
    
set(PYBIND11_NEWPYTHON ON)
find_package(pybind11 REQUIRED)
find_package(uproot-custom REQUIRED)

pybind11_add_module(my_reader_cpp
    my_reader.cc
)

target_include_directories(my_reader_cpp PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(my_reader_cpp PRIVATE uproot-custom)

if(DEFINED SKBUILD_PROJECT_NAME)
    install(
        TARGETS my_reader_cpp
        LIBRARY DESTINATION ${SKBUILD_PROJECT_NAME}
    )
endif()
