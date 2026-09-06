cmake_minimum_required(VERSION 3.15)
project(obsbot_bridge)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED SDK_ROOT)
    set(SDK_ROOT ${CMAKE_SOURCE_DIR}/../libdev_v1.0.2)
endif()

if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    set(SDK_LINK_PATH ${SDK_ROOT}/linux/x86_64-release)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64")
    set(SDK_LINK_PATH ${SDK_ROOT}/linux/arm64-release)
else()
    message(FATAL_ERROR "Unsupported architecture: ${CMAKE_SYSTEM_PROCESSOR}")
endif()

find_package(pybind11 REQUIRED)

pybind11_add_module(obsbot_bridge obsbot_bridge.cpp)

target_include_directories(obsbot_bridge PRIVATE ${SDK_ROOT}/include)
target_link_directories(obsbot_bridge PRIVATE ${SDK_LINK_PATH})
target_link_libraries(obsbot_bridge PRIVATE dev)

set_target_properties(obsbot_bridge PROPERTIES
    BUILD_RPATH "${SDK_LINK_PATH}"
    INSTALL_RPATH "${SDK_LINK_PATH}"
)
