include(${CMAKE_CURRENT_LIST_DIR}/uproot-customConfigVersion.cmake)

find_path(UPROOT_CUSTOM_INCLUDE_DIR
    NAMES uproot-custom/uproot-custom.hh
    HINTS ${CMAKE_CURRENT_LIST_DIR}/../../include
)

message(DEBUG "[DEBUG] UPROOT_CUSTOM_INCLUDE_DIR: ${UPROOT_CUSTOM_INCLUDE_DIR}")

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(uproot-custom
    DEFAULT_MSG UPROOT_CUSTOM_INCLUDE_DIR
)

if(uproot-custom_FOUND AND NOT TARGET uproot-custom)
    add_library(uproot-custom INTERFACE IMPORTED)
    target_include_directories(uproot-custom INTERFACE ${UPROOT_CUSTOM_INCLUDE_DIR})
    message(DEBUG "[DEBUG] Target uproot-custom created")
endif()
