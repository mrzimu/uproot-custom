cmake_minimum_required(VERSION 3.20)

project(gen-demo-data LANGUAGES CXX)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_BUILD_TYPE Debug)

find_package(ROOT REQUIRED COMPONENTS Core RIO Tree)

add_executable(gen-test-data
    src/main.cc
    src/TOverrideStreamer.cc
)

target_include_directories(gen-test-data
    PRIVATE ${CMAKE_CURRENT_LIST_DIR}/include
)

target_link_libraries(gen-test-data
    PRIVATE
        ROOT::Core
        ROOT::RIO
        ROOT::Tree
)

ROOT_GENERATE_DICTIONARY(MyRootDict
        ${CMAKE_CURRENT_LIST_DIR}/include/TBasicTypes.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TCStyleArray.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TComplicatedSTL.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TObjInObjArray.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TOverrideStreamer.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TRootObjects.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TSTLArray.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TSTLMap.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TSTLSequence.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TSTLString.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TSimpleObject.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TSTLSeqWithObj.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TSTLMapWithObj.hh
        ${CMAKE_CURRENT_LIST_DIR}/include/TNestedSTL.hh
    LINKDEF ${CMAKE_CURRENT_LIST_DIR}/include/LinkDef.h
    MODULE gen-test-data
)
