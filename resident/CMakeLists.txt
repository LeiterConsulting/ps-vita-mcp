cmake_minimum_required(VERSION 3.16)
set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "Vita toolchain")
project(vita_resident C)
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)
add_executable(vita_resident service.c sha256.c platform_vita.c pairing.c pairing_json.c pairing_io.c files.c files_platform_vita.c
    launch_broker/core.c launch_broker/http.c launch_broker/store.c launch_broker/native_vita.c launch_broker/service.c)
set(resident_fingerprint "")
foreach(resident_source service.c sha256.c sha256.h platform.h platform_vita.c pairing.c pairing_json.c pairing_io.c pairing.h CMakeLists.txt exports.yml files.c files.h files_platform.h files_platform_vita.c
    launch_broker/core.c launch_broker/launch_broker.h launch_broker/http.c launch_broker/http.h
    launch_broker/store.c launch_broker/store.h launch_broker/native_vita.c launch_broker/native.h
    launch_broker/service.c launch_broker/service.h)
    file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/${resident_source}" resident_digest)
    string(APPEND resident_fingerprint "${resident_digest}")
endforeach()
string(SHA256 resident_build_id "${resident_fingerprint}")
target_compile_definitions(vita_resident PRIVATE R_BUILD_ID="${resident_build_id}")
target_compile_options(vita_resident PRIVATE -std=c11 -Wall -Wextra -Werror -O2 -g -fno-builtin -fno-pic -fno-PIC)
set_target_properties(vita_resident PROPERTIES LINK_FLAGS "-nostdlib -Wl,-q")
target_link_libraries(vita_resident gcc SceLibKernel_stub_weak SceNet_stub_weak SceNetCtl_stub_weak SceSysmodule_stub_weak SceKernelThreadMgr_stub_weak SceIofilemgr_stub_weak SceProcessmgr_stub_weak ScePower_stub_weak SceRtc_stub_weak SceAppMgr_stub_weak)
vita_create_self(vita_resident.suprx vita_resident UNSAFE CONFIG ${CMAKE_CURRENT_SOURCE_DIR}/exports.yml)
