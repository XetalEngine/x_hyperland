find_package(CURL 7.85 REQUIRED)
find_package(LibArchive REQUIRED)
find_package(OpenSSL REQUIRED COMPONENTS Crypto)
find_package(Threads REQUIRED)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Concurrent)

add_library(xetal_proton_core STATIC
    src/config.cpp src/dependencies.cpp src/download.cpp src/icons.cpp
    src/launcher.cpp src/steam.cpp src/tools.cpp src/util.cpp)
set_target_properties(xetal_proton_core PROPERTIES CXX_STANDARD 20)
target_include_directories(xetal_proton_core PUBLIC src third_party)
target_link_libraries(xetal_proton_core PUBLIC CURL::libcurl LibArchive::LibArchive
    OpenSSL::Crypto Threads::Threads)

add_library(xetal_proton_page STATIC controller.cpp controller.h page.cpp page.h
    library.cpp tools_page.cpp dependencies_page.cpp)
set_target_properties(xetal_proton_page PROPERTIES CXX_STANDARD 20)
target_link_libraries(xetal_proton_page PUBLIC xetal_proton_core Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Concurrent)
target_include_directories(xetal_proton_page PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")

option(BUILD_PROTON_TESTS "Build isolated Proton backend and page tests" OFF)
if(BUILD_PROTON_TESTS)
    enable_testing()
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)
    add_executable(proton_core_tests tests/core_tests.cpp)
    set_target_properties(proton_core_tests PROPERTIES CXX_STANDARD 20)
    target_link_libraries(proton_core_tests PRIVATE xetal_proton_core)
    add_test(NAME proton_core COMMAND proton_core_tests)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    find_program(PROTON_OPENSSL openssl REQUIRED)
    add_test(NAME proton_download_recovery COMMAND ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/download_server.py"
        $<TARGET_FILE:proton_core_tests> "${PROTON_OPENSSL}")
    set_tests_properties(proton_download_recovery PROPERTIES TIMEOUT 100)
    add_executable(proton_page_tests tests/page_tests.cpp)
    set_target_properties(proton_page_tests PROPERTIES CXX_STANDARD 20)
    target_link_libraries(proton_page_tests PRIVATE xetal_proton_page Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME proton_page COMMAND proton_page_tests)
    set_tests_properties(proton_page PROPERTIES
        ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QPA_PLATFORMTHEME=;QT_PLUGIN_PATH=")
endif()
