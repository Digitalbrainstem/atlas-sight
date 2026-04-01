cmake_minimum_required(VERSION 3.22)

project("atlas-sight-vlm" VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED true)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED true)

set(CMAKE_C_FLAGS   "${CMAKE_C_FLAGS}"   CACHE STRING "" FORCE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}" CACHE STRING "" FORCE)

# --------------------------------------------------------------------------
# Android ABI configuration
# --------------------------------------------------------------------------

if(DEFINED ANDROID_ABI)
    message(STATUS "Detected Android ABI: ${ANDROID_ABI}")
    if(ANDROID_ABI STREQUAL "arm64-v8a")
        set(GGML_SYSTEM_ARCH "ARM")
        set(GGML_CPU_KLEIDIAI ON)
        set(GGML_OPENMP ON)
    elseif(ANDROID_ABI STREQUAL "x86_64")
        set(GGML_SYSTEM_ARCH "x86")
        set(GGML_CPU_KLEIDIAI OFF)
        set(GGML_OPENMP OFF)
    else()
        message(FATAL_ERROR "Unsupported ABI: ${ANDROID_ABI}")
    endif()
endif()

# --------------------------------------------------------------------------
# llama.cpp source tree
# --------------------------------------------------------------------------

if(NOT DEFINED LLAMA_SRC_DIR)
    message(FATAL_ERROR "LLAMA_SRC_DIR must be defined (path to llama.cpp source root)")
endif()

set(LLAMA_SRC ${LLAMA_SRC_DIR})
message(STATUS "llama.cpp source: ${LLAMA_SRC}")

# Build llama core (ggml, llama, common) AND tools (mtmd)
set(LLAMA_BUILD_TOOLS ON CACHE BOOL "" FORCE)
add_subdirectory(${LLAMA_SRC} build-llama)

# --------------------------------------------------------------------------
# Atlas Sight VLM JNI bridge
# --------------------------------------------------------------------------

add_library(${CMAKE_PROJECT_NAME} SHARED
        vision_chat.cpp)

target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE
        ${LLAMA_SRC}
        ${LLAMA_SRC}/common
        ${LLAMA_SRC}/include
        ${LLAMA_SRC}/ggml/include
        ${LLAMA_SRC}/ggml/src
        ${LLAMA_SRC}/tools/mtmd)

target_link_libraries(${CMAKE_PROJECT_NAME}
        llama
        common
        mtmd
        android
        log)
