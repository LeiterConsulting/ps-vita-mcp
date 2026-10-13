cmake_minimum_required(VERSION 3.16)
set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "Vita toolchain")
project(vita_native_app_slot C)
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)
get_filename_component(slot_root "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)
if(NOT SLOT_PROJECT MATCHES "^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$" OR SLOT_PROJECT MATCHES "(^|/)\\.\\.?(/|$)"
        OR NOT SLOT_CONFIG MATCHES "^[A-Za-z0-9_./-]+$" OR SLOT_CONFIG MATCHES "(^|/)\\.\\.?(/|$)"
        OR NOT LAB_VERSION MATCHES "^[0-9][0-9]\\.[0-9][0-9]$" OR NOT LAB_BUILD_ID MATCHES "^[a-f0-9]+$")
    message(FATAL_ERROR "Use the validated native-slot builder with safe repository-relative inputs")
endif()
string(LENGTH "${LAB_BUILD_ID}" id_length)
if(NOT id_length EQUAL 64)
    message(FATAL_ERROR "Expected exact native build identity")
endif()
set(slot_project "${slot_root}/${SLOT_PROJECT}")
add_executable(native_lab main.c "${slot_project}/app.c" "${slot_project}/app_sim.c"
    "${slot_root}/lifecycle_lab/lab_core.c" "${slot_root}/lifecycle_lab/lab_server.c"
    "${slot_root}/lifecycle_lab/lab_platform_vita.c")
target_include_directories(native_lab PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${slot_project}"
    "${slot_root}/lifecycle_lab" "${slot_root}/${SLOT_CONFIG}")
target_compile_definitions(native_lab PRIVATE LAB_VERSION="${LAB_VERSION}" LAB_VARIANT=1 LAB_BUILD_ID="${LAB_BUILD_ID}")
target_compile_options(native_lab PRIVATE -std=c11 -O2 -g -Wall -Wextra -Werror)
target_link_libraries(native_lab vita2d SceDisplay_stub SceGxm_stub SceSysmodule_stub SceCtrl_stub ScePgf_stub ScePvf_stub
    SceCommonDialog_stub SceAppMgr_stub SceNet_stub SceNetCtl_stub SceKernelThreadMgr_stub SceLibKernel_stub freetype png jpeg z m)
vita_create_self(native_lab.self native_lab UNSAFE STRIPPED UNCOMPRESSED)
set(VITA_MKSFOEX_FLAGS "-d PARENTAL_LEVEL=1")
vita_create_vpk(native_lab.vpk VMCP00001 native_lab.self VERSION "${LAB_VERSION}" NAME "Vita Development Slot"
    FILE "${slot_root}/lifecycle_lab/assets/icon0.png" sce_sys/icon0.png
    FILE "${slot_root}/lifecycle_lab/assets/bg.png" sce_sys/livearea/contents/bg.png
    FILE "${slot_root}/lifecycle_lab/assets/startup.png" sce_sys/livearea/contents/startup.png
    FILE "${slot_root}/lifecycle_lab/assets/template.xml" sce_sys/livearea/contents/template.xml
    FILE "${slot_root}/LICENSE" LICENSE)
