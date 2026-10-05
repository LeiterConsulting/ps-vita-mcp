cmake_minimum_required(VERSION 3.16)
set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "Vita toolchain")
project(vita_input_target C)
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)
set(fingerprint "")
foreach(source main.c telemetry.c telemetry.h protocol.c protocol.h server.c platform_vita.c CMakeLists.txt ../../common/platform.h ../../common/math_helpers.c ../../common/math_helpers.h)
    file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/${source}" digest)
    string(APPEND fingerprint "${digest}")
endforeach()
string(SHA256 build_id "${fingerprint}")
add_executable(input_target main.c telemetry.c protocol.c server.c platform_vita.c ../../common/math_helpers.c)
target_include_directories(input_target PRIVATE ../../common)
target_compile_definitions(input_target PRIVATE TARGET_BUILD_ID="${build_id}")
target_compile_options(input_target PRIVATE -std=c11 -g -O2 -Wall -Wextra -Werror)
target_link_libraries(input_target vita2d SceDisplay_stub SceGxm_stub SceSysmodule_stub SceCtrl_stub SceTouch_stub SceMotion_stub ScePgf_stub ScePvf_stub SceCommonDialog_stub SceAppMgr_stub SceNet_stub SceNetCtl_stub SceKernelThreadMgr_stub freetype png jpeg z m)
vita_create_self(input_target.self input_target UNSAFE)
vita_create_vpk(input_target.vpk CHRS00012 input_target.self VERSION "01.00" NAME "Vita Input Target"
 FILE assets/icon0.png sce_sys/icon0.png FILE assets/bg.png sce_sys/livearea/contents/bg.png
 FILE assets/startup.png sce_sys/livearea/contents/startup.png
 FILE ../../assets/template.xml sce_sys/livearea/contents/template.xml
 FILE ../../LICENSE LICENSE)
