cmake_minimum_required(VERSION 3.16)

project(CachyOsTools VERSION 0.1 LANGUAGES C CXX)

set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Widgets Network DBus)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Widgets Network DBus)
find_package(PkgConfig REQUIRED)
pkg_check_modules(WINDOW_ENUM_X11 REQUIRED IMPORTED_TARGET xcb xcb-res)
pkg_check_modules(WINDOW_ENUM_WAYLAND REQUIRED IMPORTED_TARGET wayland-client)
find_program(WAYLAND_SCANNER wayland-scanner REQUIRED)
set(WINDOW_ENUM_PROTOCOL_DIR "${CMAKE_CURRENT_BINARY_DIR}/window-enum-protocols")
file(MAKE_DIRECTORY "${WINDOW_ENUM_PROTOCOL_DIR}")
foreach(protocol wlr-foreign-toplevel-management-unstable-v1 ext-foreign-toplevel-list-v1)
    set(xml "${CMAKE_CURRENT_SOURCE_DIR}/window_enum/protocols/${protocol}.xml")
    set(header "${WINDOW_ENUM_PROTOCOL_DIR}/${protocol}-client.h")
    set(code "${WINDOW_ENUM_PROTOCOL_DIR}/${protocol}-protocol.c")
    add_custom_command(OUTPUT "${header}" "${code}"
        COMMAND "${WAYLAND_SCANNER}" client-header "${xml}" "${header}"
        COMMAND "${WAYLAND_SCANNER}" private-code "${xml}" "${code}"
        DEPENDS "${xml}" VERBATIM)
    list(APPEND WINDOW_ENUM_PROTOCOLS "${header}" "${code}")
endforeach()

set(PROJECT_SOURCES
        ../main.cpp
        ../native.cpp
        ../native.h
    ../wheel_guard.h
    ../disk_visualizer.cpp
    ../disk_visualizer.h
    ../disk_layout.h
    ../ram_cleaner.cpp
    ../ram_cleaner.h
    ../default_apps.cpp
    ../default_apps.h
    ../grub_editor.cpp
    ../grub_editor.h
    ../grub_appearance.cpp
    ../grub_appearance.h
    ../runtime_log_guard.cpp
    ../runtime_log_guard.h
        mainwindow.cpp
        mainwindow.h
        mainwindow.ui
        isoexclusionsdialog.ui
        # Header files containing implementations
        dual_gpu_kvm.h
        single_gpu_kvm.h
        device_manager.h
        users_groups.h
        restore_points.h
        firewall_manager.h
        kernel_manager.h
        ../kernel_catalog.h
        env_editor.h
        system_properties.h
        drive.h
        drive_tree.h
        drive_tree.cpp
        drivelabel.h
        drivelabel.cpp
        mainwindow_d.h
        systembackup.h
        systemrestore.h
        systemlogs.h
        systemconfigs.h
        tweaks.h
        kde_tweaks.h
        kde_fixes.h
        shell.h
        executecommands.h
        current_system_iso_creator.h
        services.h
        includes.h
        uninstalltab.h
        tabupgrades.h
        thememanager.h
        themepresets.h
        preferences.h
        preferencesdialog.h
        preferencesdialog.cpp
        dashboard.h
        isoexclusions.h
        cleaner.h
        script_helpers.h
        file_manager.h
        package_install.h
        pacman_doctor.h
        sensors_power.h
        network_shares.h
        autostart.h
        window_enum.h
        window_enum.cpp
        window_enum_controller.cpp
        window_enum_backend.h
        window_enum_backend.cpp
        window_enum_x11.cpp
        window_enum_wayland.cpp
        ${WINDOW_ENUM_PROTOCOLS}
        resources.qrc
        # Additional files (currently empty but may be implemented)
        drivetools.h
        drivetools.cpp
)

if(${QT_VERSION_MAJOR} GREATER_EQUAL 6)
    qt_add_executable(CachyOsTools
        MANUAL_FINALIZATION
        ${PROJECT_SOURCES}
    )
# Define target properties for Android with Qt 6 as:
#    set_property(TARGET CachyOsTools APPEND PROPERTY QT_ANDROID_PACKAGE_SOURCE_DIR
#                 ${CMAKE_CURRENT_SOURCE_DIR}/android)
# For more information, see https://doc.qt.io/qt-6/qt-add-executable.html#target-creation
else()
    if(ANDROID)
        add_library(CachyOsTools SHARED
            ${PROJECT_SOURCES}
        )
# Define properties for Android with Qt 5 after find_package() calls as:
#    set(ANDROID_PACKAGE_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/android")
    else()
        add_executable(CachyOsTools
            ${PROJECT_SOURCES}
        )
    endif()
endif()

option(BUILD_KERNEL_CATALOG_TESTS "Build isolated kernel catalogue interface checks" OFF)
if(BUILD_KERNEL_CATALOG_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(kernel_catalog_tests tests/kernel_catalog_tests.cpp ../kernel_catalog.h)
    target_include_directories(kernel_catalog_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(kernel_catalog_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME kernel_catalog COMMAND kernel_catalog_tests)
    set_tests_properties(kernel_catalog PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()

option(BUILD_GRUB_EDITOR_TESTS "Build isolated GRUB editor interface checks" OFF)
if(BUILD_GRUB_EDITOR_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(grub_editor_tests tests/grub_editor_tests.cpp ../grub_editor.cpp ../grub_editor.h ../grub_appearance.cpp ../grub_appearance.h)
    target_include_directories(grub_editor_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(grub_editor_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME grub_editor COMMAND grub_editor_tests)
    set_tests_properties(grub_editor PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()

option(BUILD_RUNTIME_LOG_GUARD_TESTS "Build isolated session log guard interface checks" OFF)
if(BUILD_RUNTIME_LOG_GUARD_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(runtime_log_guard_tests tests/runtime_log_guard_tests.cpp ../runtime_log_guard.cpp ../runtime_log_guard.h)
    target_include_directories(runtime_log_guard_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(runtime_log_guard_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME runtime_log_guard COMMAND runtime_log_guard_tests)
    set_tests_properties(runtime_log_guard PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()

target_link_libraries(CachyOsTools PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Network Qt${QT_VERSION_MAJOR}::DBus)
target_link_libraries(CachyOsTools PRIVATE PkgConfig::WINDOW_ENUM_X11 PkgConfig::WINDOW_ENUM_WAYLAND)
target_include_directories(CachyOsTools PRIVATE "${WINDOW_ENUM_PROTOCOL_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/..")
set_target_properties(CachyOsTools PROPERTIES OUTPUT_NAME xetal-control-panel)

option(BUILD_WINDOW_ENUM_TESTS "Build isolated window enumeration tests" OFF)
if(BUILD_WINDOW_ENUM_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_executable(window_enum_tests tests/window_enum_tests.cpp window_enum.h
        window_enum.cpp window_enum_controller.cpp window_enum_backend.cpp window_enum_x11.cpp resources.qrc)
    target_include_directories(window_enum_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    target_link_libraries(window_enum_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets
        Qt${QT_VERSION_MAJOR}::DBus Qt${QT_VERSION_MAJOR}::Test PkgConfig::WINDOW_ENUM_X11)
    add_test(NAME window_enum_x11 COMMAND "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_window_enum_tests.py" $<TARGET_FILE:window_enum_tests>)
    pkg_check_modules(WINDOW_ENUM_SERVER REQUIRED IMPORTED_TARGET wayland-server)
    foreach(protocol wlr-foreign-toplevel-management-unstable-v1 ext-foreign-toplevel-list-v1)
        set(header "${WINDOW_ENUM_PROTOCOL_DIR}/${protocol}-server.h")
        add_custom_command(OUTPUT "${header}"
            COMMAND "${WAYLAND_SCANNER}" server-header
                "${CMAKE_CURRENT_SOURCE_DIR}/window_enum/protocols/${protocol}.xml" "${header}"
            DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/window_enum/protocols/${protocol}.xml" VERBATIM)
        list(APPEND WINDOW_ENUM_SERVER_HEADERS "${header}")
    endforeach()
    add_executable(window_enum_wayland_fixture tests/window_enum_wayland_fixture.cpp
        ${WINDOW_ENUM_PROTOCOLS} ${WINDOW_ENUM_SERVER_HEADERS})
    target_include_directories(window_enum_wayland_fixture PRIVATE "${WINDOW_ENUM_PROTOCOL_DIR}")
    target_link_libraries(window_enum_wayland_fixture PRIVATE PkgConfig::WINDOW_ENUM_SERVER)
    add_test(NAME window_enum_wayland COMMAND "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_window_enum_wayland_tests.py"
        $<TARGET_FILE:CachyOsTools> $<TARGET_FILE:window_enum_wayland_fixture>)
endif()

option(BUILD_PREFERENCES_TESTS "Build preferences dialog and persistence tests" OFF)
option(BUILD_WHEEL_GUARD_TESTS "Build settings wheel interaction tests" OFF)
option(BUILD_DISK_VISUALIZER_TESTS "Build disk map layout and UI tests" OFF)
option(BUILD_RAM_CLEANER_TESTS "Build isolated RAM cleaner interaction tests" OFF)
option(BUILD_DEFAULT_APPS_TESTS "Build isolated default-app interaction tests" OFF)
if(BUILD_DEFAULT_APPS_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(default_apps_tests tests/default_apps_tests.cpp ../default_apps.cpp ../default_apps.h)
    target_include_directories(default_apps_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(default_apps_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME default_apps COMMAND default_apps_tests)
    set_tests_properties(default_apps PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()
if(BUILD_RAM_CLEANER_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(ram_cleaner_tests tests/ram_cleaner_tests.cpp ../ram_cleaner.cpp ../ram_cleaner.h)
    target_include_directories(ram_cleaner_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(ram_cleaner_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME ram_cleaner COMMAND ram_cleaner_tests)
    set_tests_properties(ram_cleaner PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()
if(BUILD_DISK_VISUALIZER_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(disk_visualizer_tests tests/disk_visualizer_tests.cpp
        ../disk_visualizer.cpp ../disk_visualizer.h ../disk_layout.h)
    target_include_directories(disk_visualizer_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(disk_visualizer_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets
        Qt${QT_VERSION_MAJOR}::DBus Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME disk_visualizer COMMAND disk_visualizer_tests)
    set_tests_properties(disk_visualizer PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()
if(BUILD_WHEEL_GUARD_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(wheel_guard_tests tests/wheel_guard_tests.cpp ../wheel_guard.h)
    target_include_directories(wheel_guard_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(wheel_guard_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME settings_wheel_guard COMMAND wheel_guard_tests)
    set_tests_properties(settings_wheel_guard PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()
option(BUILD_LOG_READER_TESTS "Build plain text report/stream tests" OFF)
if(BUILD_LOG_READER_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(log_reader_tests tests/log_reader_tests.cpp log_reader.h)
    target_include_directories(log_reader_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    target_link_libraries(log_reader_tests PRIVATE Qt${QT_VERSION_MAJOR}::Core Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME log_reader COMMAND log_reader_tests)
endif()
if(BUILD_PREFERENCES_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(preferences_dialog_tests tests/preferences_dialog_tests.cpp
        preferencesdialog.cpp preferencesdialog.h themepresets.h)
    target_include_directories(preferences_dialog_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    target_link_libraries(preferences_dialog_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME preferences_dialog COMMAND preferences_dialog_tests)
    set_tests_properties(preferences_dialog PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()

option(BUILD_DRIVE_LABEL_TESTS "Build isolated volume label tests" OFF)
if(BUILD_DRIVE_LABEL_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(drive_label_tests tests/drive_label_tests.cpp drivelabel.cpp drivelabel.h)
    target_include_directories(drive_label_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    target_link_libraries(drive_label_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets
        Qt${QT_VERSION_MAJOR}::DBus Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME drive_label COMMAND drive_label_tests)
    set_tests_properties(drive_label PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()

option(BUILD_FILE_MANAGER_TESTS "Build isolated folder-opening tests" OFF)
if(BUILD_FILE_MANAGER_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    find_program(DBUS_RUN_SESSION dbus-run-session REQUIRED)
    add_executable(file_manager_tests tests/file_manager_tests.cpp file_manager.h)
    target_include_directories(file_manager_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    target_link_libraries(file_manager_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets
        Qt${QT_VERSION_MAJOR}::DBus Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME file_manager COMMAND "${DBUS_RUN_SESSION}"
        "--config-file=${CMAKE_CURRENT_SOURCE_DIR}/tests/file_manager_bus.conf"
        -- $<TARGET_FILE:file_manager_tests>)
    set_tests_properties(file_manager PROPERTIES
        ENVIRONMENT "CACHY_FILE_MANAGER_TEST_BUS=1;QT_QPA_PLATFORM=offscreen;QT_QPA_PLATFORMTHEME="
        TIMEOUT 30)
endif()

# GUI translations (pt_BR, de). Skipped gracefully when LinguistTools is not
# installed — the app then simply runs in English.
if(${QT_VERSION_MAJOR} GREATER_EQUAL 6)
    find_package(Qt6 REQUIRED COMPONENTS LinguistTools)
    if(Qt6LinguistTools_FOUND)
        qt_add_translations(CachyOsTools TS_FILES
            translations/cachyostools_pt_BR.ts
            translations/cachyostools_de.ts)
    endif()
endif()

# Qt for iOS sets MACOSX_BUNDLE_GUI_IDENTIFIER automatically since Qt 6.1.
# If you are developing for iOS or macOS you should consider setting an
# explicit, fixed bundle identifier manually though.
if(${QT_VERSION} VERSION_LESS 6.1.0)
  set(BUNDLE_ID_OPTION MACOSX_BUNDLE_GUI_IDENTIFIER com.example.CachyOsTools)
endif()
set_target_properties(CachyOsTools PROPERTIES
    ${BUNDLE_ID_OPTION}
    MACOSX_BUNDLE_BUNDLE_VERSION ${PROJECT_VERSION}
    MACOSX_BUNDLE_SHORT_VERSION_STRING ${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}
    MACOSX_BUNDLE TRUE
    WIN32_EXECUTABLE TRUE
)

include(GNUInstallDirs)
install(TARGETS CachyOsTools
    BUNDLE DESTINATION .
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

if(QT_VERSION_MAJOR EQUAL 6)
    qt_finalize_executable(CachyOsTools)
endif()

option(BUILD_DRIVE_TREE_TESTS "Build disk tree and window-size checks" OFF)
if(BUILD_DRIVE_TREE_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(drive_tree_tests tests/drive_tree_tests.cpp drive_tree.cpp drivelabel.cpp)
    target_include_directories(drive_tree_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    target_link_libraries(drive_tree_tests PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::DBus Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME drive_tree COMMAND drive_tree_tests)
    set_tests_properties(drive_tree PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()
