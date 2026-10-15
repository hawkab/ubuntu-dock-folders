cmake_minimum_required(VERSION 3.22)
project(DockFolderEffects LANGUAGES C CXX)
include(../kwin-backdrop/identity.cmake)
set(CMAKE_AUTOMOC ON)
set(CMAKE_CXX_STANDARD 17)
find_package(Qt6 6.6 REQUIRED COMPONENTS Gui Qml Quick DBus)
find_package(Qt6GuiPrivate REQUIRED)
find_package(KF6WindowSystem REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(WAYLAND_CLIENT REQUIRED IMPORTED_TARGET wayland-client)
find_program(WAYLAND_SCANNER wayland-scanner REQUIRED)
add_custom_command(OUTPUT wayland-blur-client.h wayland-blur-protocol.c
    COMMAND ${WAYLAND_SCANNER} client-header ${CMAKE_CURRENT_SOURCE_DIR}/blur.xml wayland-blur-client.h
    COMMAND ${WAYLAND_SCANNER} private-code ${CMAKE_CURRENT_SOURCE_DIR}/blur.xml wayland-blur-protocol.c
    DEPENDS blur.xml)
add_library(dockfolderseffects MODULE plugin.cpp windoweffects.cpp backdropblur.cpp waylandblur.cpp taskidentity.cpp
    ${CMAKE_CURRENT_BINARY_DIR}/wayland-blur-protocol.c)
target_include_directories(dockfolderseffects PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
target_compile_definitions(dockfolderseffects PRIVATE DOCK_BACKDROP_PLUGIN_ID="${DOCK_BACKDROP_PLUGIN}")
target_link_libraries(dockfolderseffects PRIVATE Qt6::GuiPrivate Qt6::Qml Qt6::Quick Qt6::DBus
    KF6::WindowSystem PkgConfig::WAYLAND_CLIENT)
target_compile_options(dockfolderseffects PRIVATE -Wall -Wextra -Werror)
install(TARGETS dockfolderseffects LIBRARY DESTINATION contents/effects)
add_executable(dock-folders-core-runner ../core-runner.cpp)
target_link_libraries(dock-folders-core-runner PRIVATE Qt6::Qml)
target_compile_options(dock-folders-core-runner PRIVATE -Wall -Wextra -Werror)
install(TARGETS dock-folders-core-runner RUNTIME DESTINATION contents/code)
