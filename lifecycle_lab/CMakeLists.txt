cmake_minimum_required(VERSION 3.16)
set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "Vita toolchain")
project(vita_native_lifecycle_lab C)
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)
set(LAB_VERSION "01.00" CACHE STRING "Fixed native lab candidate version")
set(LAB_VARIANT "1" CACHE STRING "Fixed native lab evaluation variant")
if(NOT LAB_VERSION MATCHES "^[0-9][0-9]\\.[0-9][0-9]$" OR NOT LAB_VARIANT MATCHES "^[12]$")
    message(FATAL_ERROR "Choose a canonical Vita version and lab variant 1 or 2")
endif()
set(lab_sources main.c lab_core.c lab_core.h lab_platform.h lab_platform_vita.c lab_server.c lab_server.h CMakeLists.txt)
set(fingerprint "${LAB_VERSION}:${LAB_VARIANT}:")
foreach(source IN LISTS lab_sources)
    file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/${source}" hash)
    string(APPEND fingerprint "${hash}")
endforeach()
string(SHA256 LAB_NATIVE_BUILD_ID "${fingerprint}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/native-build-id.txt" "${LAB_NATIVE_BUILD_ID}\n")
add_executable(native_lab main.c lab_core.c lab_server.c lab_platform_vita.c)
target_compile_definitions(native_lab PRIVATE LAB_VERSION="${LAB_VERSION}" LAB_VARIANT=${LAB_VARIANT} LAB_BUILD_ID="${LAB_NATIVE_BUILD_ID}")
target_compile_options(native_lab PRIVATE -std=c11 -O2 -g -Wall -Wextra -Werror)
target_link_libraries(native_lab vita2d SceDisplay_stub SceGxm_stub SceSysmodule_stub SceCtrl_stub ScePgf_stub ScePvf_stub
    SceCommonDialog_stub SceAppMgr_stub SceNet_stub SceNetCtl_stub SceKernelThreadMgr_stub SceLibKernel_stub freetype png jpeg z m)
vita_create_self(native_lab.self native_lab UNSAFE STRIPPED UNCOMPRESSED)
set(VITA_MKSFOEX_FLAGS "-d PARENTAL_LEVEL=1")
vita_create_vpk(native_lab.vpk VMCP00001 native_lab.self VERSION "${LAB_VERSION}" NAME "Vita Lifecycle Lab"
    FILE assets/icon0.png sce_sys/icon0.png
    FILE assets/bg.png sce_sys/livearea/contents/bg.png
    FILE assets/startup.png sce_sys/livearea/contents/startup.png
    FILE assets/template.xml sce_sys/livearea/contents/template.xml
    FILE ../LICENSE LICENSE)
