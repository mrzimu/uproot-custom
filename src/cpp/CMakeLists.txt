pybind11_add_module(_cpp
    src/uproot-custom-cpp.cc
)

target_include_directories(_cpp
    PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

install(TARGETS _cpp LIBRARY DESTINATION ${SKBUILD_PROJECT_NAME})
