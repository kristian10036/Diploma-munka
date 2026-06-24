cmake_minimum_required(VERSION 3.16)
project(diploma_rf_agent VERSION 0.2.0 LANGUAGES CXX)

if(POLICY CMP0167)
    cmake_policy(SET CMP0167 NEW)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(BUILD_TESTING "Build RF agent tests" ON)
option(ENABLE_AARONIA "Build isolated Aaronia helper processes" ON)
option(ENABLE_USRP "Enable Ettus USRP UHD support" OFF)

find_package(OpenSSL REQUIRED)
find_package(Boost REQUIRED)
find_package(Threads REQUIRED)
find_package(SoapySDR CONFIG REQUIRED)
find_library(ZSTD_LIBRARY NAMES zstd REQUIRED)

add_library(rf_agent_models
    src/models.cpp
    src/rf_source.cpp
    src/mock_rf_source.cpp
    src/replay_rf_source.cpp
    src/recording_writer.cpp
    src/aaronia_probe_runner.cpp
    src/aaronia_rf_source.cpp
    src/soapy_rf_source.cpp
    src/auto_rf_source.cpp
    src/usrp_probe_runner.cpp
    src/sdrangel_client.cpp
    src/sdrangel_demod_settings.cpp
    src/dsp/fft_pipeline.cpp
    src/frame_json.cpp
    src/agent.cpp
)
target_include_directories(rf_agent_models PUBLIC include ${Boost_INCLUDE_DIRS} ${SoapySDR_INCLUDE_DIRS})
set(RF_AGENT_BOOST_TARGET "")
if(TARGET Boost::headers)
    set(RF_AGENT_BOOST_TARGET Boost::headers)
elseif(TARGET Boost::boost)
    set(RF_AGENT_BOOST_TARGET Boost::boost)
endif()
set(RF_AGENT_SOAPY_TARGET ${SoapySDR_LIBRARIES})
if(TARGET SoapySDR::SoapySDR)
    set(RF_AGENT_SOAPY_TARGET SoapySDR::SoapySDR)
elseif(TARGET SoapySDR)
    set(RF_AGENT_SOAPY_TARGET SoapySDR)
endif()
target_link_libraries(rf_agent_models PUBLIC OpenSSL::Crypto ${ZSTD_LIBRARY} Threads::Threads ${RF_AGENT_BOOST_TARGET} ${RF_AGENT_SOAPY_TARGET})
target_compile_definitions(rf_agent_models PUBLIC BOOST_ERROR_CODE_HEADER_ONLY)
target_compile_options(rf_agent_models PRIVATE -Wall -Wextra -Wpedantic)

if(BUILD_TESTING)
    enable_testing()
    add_executable(rf_agent_models_test tests/test_models.cpp)
    target_link_libraries(rf_agent_models_test PRIVATE rf_agent_models)
    target_compile_options(rf_agent_models_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME rf_agent_models_test COMMAND rf_agent_models_test)

    add_executable(rf_agent_mock_test tests/test_mock_rf_source.cpp)
    target_link_libraries(rf_agent_mock_test PRIVATE rf_agent_models)
    target_compile_options(rf_agent_mock_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME rf_agent_mock_test COMMAND rf_agent_mock_test)

    add_executable(rf_agent_replay_test tests/test_replay_rf_source.cpp)
    target_link_libraries(rf_agent_replay_test PRIVATE rf_agent_models)
    target_compile_options(rf_agent_replay_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME rf_agent_replay_test COMMAND rf_agent_replay_test)

    add_executable(rf_agent_recording_test tests/test_recording_writer.cpp)
    target_link_libraries(rf_agent_recording_test PRIVATE rf_agent_models)
    target_compile_options(rf_agent_recording_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME rf_agent_recording_test COMMAND rf_agent_recording_test)

    add_executable(rf_agent_source_manager_test tests/test_source_manager.cpp)
    target_link_libraries(rf_agent_source_manager_test PRIVATE rf_agent_models)
    target_compile_options(rf_agent_source_manager_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME rf_agent_source_manager_test COMMAND rf_agent_source_manager_test)

    add_executable(aaronia_probe_test_child tests/probe_test_child.cpp)
    add_executable(aaronia_probe_runner_test tests/test_aaronia_probe_runner.cpp)
    target_link_libraries(aaronia_probe_runner_test PRIVATE rf_agent_models)
    target_compile_definitions(aaronia_probe_runner_test PRIVATE
        TEST_PROBE_PATH="$<TARGET_FILE:aaronia_probe_test_child>")
    target_compile_options(aaronia_probe_runner_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME aaronia_probe_runner_test COMMAND aaronia_probe_runner_test)

    add_executable(aaronia_worker_test_child tests/worker_test_child.cpp)
    add_executable(aaronia_rf_source_test tests/test_aaronia_rf_source.cpp)
    target_link_libraries(aaronia_rf_source_test PRIVATE rf_agent_models)
    target_compile_definitions(aaronia_rf_source_test PRIVATE
        TEST_WORKER_PATH="$<TARGET_FILE:aaronia_worker_test_child>")
    target_compile_options(aaronia_rf_source_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME aaronia_rf_source_test COMMAND aaronia_rf_source_test)

    add_executable(usrp_probe_runner_test tests/test_usrp_probe_runner.cpp)
    target_link_libraries(usrp_probe_runner_test PRIVATE rf_agent_models)
    target_compile_definitions(usrp_probe_runner_test PRIVATE
        TEST_PROBE_PATH="$<TARGET_FILE:aaronia_probe_test_child>")
    target_compile_options(usrp_probe_runner_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME usrp_probe_runner_test COMMAND usrp_probe_runner_test)

    add_executable(sdrangel_client_test tests/test_sdrangel_client.cpp)
    target_link_libraries(sdrangel_client_test PRIVATE rf_agent_models)
    target_compile_options(sdrangel_client_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME sdrangel_client_test COMMAND sdrangel_client_test)

    add_executable(sdrangel_demod_settings_test tests/test_sdrangel_demod_settings.cpp)
    target_link_libraries(sdrangel_demod_settings_test PRIVATE rf_agent_models)
    target_compile_options(sdrangel_demod_settings_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME sdrangel_demod_settings_test COMMAND sdrangel_demod_settings_test)

    add_executable(rf_agent_fft_test tests/test_fft_pipeline.cpp)
    target_link_libraries(rf_agent_fft_test PRIVATE rf_agent_models)
    target_compile_options(rf_agent_fft_test PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME rf_agent_fft_test COMMAND rf_agent_fft_test)
endif()

add_executable(rf-agent
    src/main.cpp
    src/http_server.cpp
)
target_link_libraries(rf-agent PRIVATE rf_agent_models Threads::Threads)
target_compile_options(rf-agent PRIVATE -Wall -Wextra -Wpedantic)

if(ENABLE_AARONIA)
    add_executable(aaronia-probe src/aaronia_probe_main.cpp)
    target_link_libraries(aaronia-probe PRIVATE ${CMAKE_DL_LIBS})
    target_compile_options(aaronia-probe PRIVATE -Wall -Wextra -Wpedantic)
    add_executable(aaronia-worker src/aaronia_worker_main.cpp)
    target_link_libraries(aaronia-worker PRIVATE ${CMAKE_DL_LIBS})
    target_compile_options(aaronia-worker PRIVATE -Wall -Wextra -Wpedantic)
    if(BUILD_TESTING)
        add_test(NAME aaronia_probe_sdk_not_found COMMAND
            ${CMAKE_COMMAND} -E env
            AARONIA_RTSA_LIBRARY_PATH=/definitely/missing/libAaroniaRTSAAPI.so
            $<TARGET_FILE:aaronia-probe>)
        set_tests_properties(aaronia_probe_sdk_not_found PROPERTIES WILL_FAIL TRUE)
    endif()
endif()

if(ENABLE_USRP)
    find_package(UHD REQUIRED)
    add_executable(usrp-probe src/usrp_probe_main.cpp)
    target_include_directories(usrp-probe PRIVATE ${UHD_INCLUDE_DIRS})
    if(TARGET UHD::uhd)
        target_link_libraries(usrp-probe PRIVATE UHD::uhd)
    else()
        target_link_libraries(usrp-probe PRIVATE ${UHD_LIBRARIES})
    endif()
    target_compile_options(usrp-probe PRIVATE -Wall -Wextra -Wpedantic)
endif()
