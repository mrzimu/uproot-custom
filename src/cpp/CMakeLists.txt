pybind11_add_module(_cpp
    src/uproot-custom-cpp.cc
)

target_include_directories(_cpp
    PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
install(TARGETS _cpp LIBRARY DESTINATION ${SKBUILD_PROJECT_NAME})

install(DIRECTORY include/ DESTINATION ${SKBUILD_PROJECT_NAME}/include)

write_basic_package_version_file(
    uproot-customConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

install(FILES
    ${CMAKE_CURRENT_LIST_DIR}/share/cmake/uproot-customConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/uproot-customConfigVersion.cmake
    DESTINATION ${SKBUILD_PROJECT_NAME}/share/cmake/
)

install(DIRECTORY
    ${CMAKE_CURRENT_SOURCE_DIR}/share/pkgconfig
    DESTINATION ${SKBUILD_PROJECT_NAME}/share
)