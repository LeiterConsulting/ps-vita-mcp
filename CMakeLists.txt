cmake_minimum_required(VERSION 3.16)
if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  if(DEFINED ENV{VITASDK})
    set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "Vita toolchain")
  else()
    message(FATAL_ERROR "Build with Build-DevLoop.ps1 or set VITASDK.")
  endif()
endif()
project(ps_vita_mcp C)
include("${VITASDK}/share/vita.cmake" REQUIRED)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(VITA_MKSFOEX_FLAGS "-d PARENTAL_LEVEL=1")

function(add_vita_app target app_name title_id app_source)
  set(app_version "01.01")
  if(ARGC GREATER 4)
    set(app_version "${ARGV4}")
  endif()
  add_executable(${target} ${app_source} common/platform_vita.c common/ui.c common/math_helpers.c)
  target_include_directories(${target} PRIVATE common)
  target_compile_options(${target} PRIVATE -g -Wall -Wextra -Werror -Wno-unused-parameter)
  target_link_libraries(${target} vita2d SceDisplay_stub SceGxm_stub SceSysmodule_stub
    SceCtrl_stub SceTouch_stub SceMotion_stub ScePgf_stub ScePvf_stub
    SceCommonDialog_stub SceAppMgr_stub freetype png jpeg z m)
  vita_create_self(${target}.self ${target} UNSAFE STRIPPED)
  set(vita_extra_files)
  if(target STREQUAL "vita_devloop")
    list(APPEND vita_extra_files FILE assets/devloop-licenses.txt licenses.txt)
  endif()
  vita_create_vpk(${target}.vpk ${title_id} ${target}.self
    VERSION "${app_version}" NAME "${app_name}"
    FILE assets/${target}/icon0.png sce_sys/icon0.png
    FILE assets/${target}/bg.png sce_sys/livearea/contents/bg.png
    FILE assets/${target}/startup.png sce_sys/livearea/contents/startup.png
    FILE assets/template.xml sce_sys/livearea/contents/template.xml ${vita_extra_files})
endfunction()

file(GLOB DEVLOOP_LUA_SOURCES CONFIGURE_DEPENDS third_party/lua-5.4.9/src/*.c)
list(FILTER DEVLOOP_LUA_SOURCES EXCLUDE REGEX "/(lua|luac|linit|ldblib|liolib|loslib|loadlib|lcorolib)\\.c$")
add_library(devloop_lua STATIC ${DEVLOOP_LUA_SOURCES})
target_include_directories(devloop_lua PUBLIC third_party/lua-5.4.9/src)
add_vita_app(vita_devloop "Vita DevLoop" CHRS00003 apps/vita_devloop.c "01.03")
target_sources(vita_devloop PRIVATE common/physics.c devloop/core.c devloop/server_vita.c devloop/script_runtime.c devloop/sha256.c)
target_include_directories(vita_devloop PRIVATE devloop)
target_link_libraries(vita_devloop devloop_lua SceNet_stub SceNetCtl_stub SceDisplay_stub SceKernelThreadMgr_stub)
