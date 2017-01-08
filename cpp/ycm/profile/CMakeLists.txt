# Copyright (C) 2017 ycmd contributors
#
# This file is part of ycmd.
#
# ycmd is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ycmd is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ycmd.  If not, see <http://www.gnu.org/licenses/>.


project( ycm_core_benchmark )
cmake_minimum_required( VERSION 2.8 )

add_subdirectory( google-benchmark )

set( BENCHMARK_INCLUDE_DIRS ${benchmark_SOURCE_DIR}/include )
set( BENCHMARK_LIBRARIES benchmark )

include_directories(
  SYSTEM
  ${ycm_core_SOURCE_DIR}
  ${BENCHMARK_INCLUDE_DIRS}
  )

link_directories(
  ${Boost_LIBRARY_DIRS}
  ${PYTHON_LIBRARIES}
)


file( GLOB_RECURSE SOURCES src/*.h src/*.cpp )

add_executable(
  ${PROJECT_NAME}
  ${SOURCES}
  )

target_link_libraries(
  ${PROJECT_NAME}
  ycm_core
  ${BENCHMARK_LIBRARIES}
  )

if ( NOT CMAKE_GENERATOR_IS_XCODE )
  # The test executable expects a "testdata" dir in its working directory. Why?
  # Because there's NO reliable, cross-platform way of getting the directory in
  # which the executable is located.
  add_custom_target( copy_testdata_profile
                     COMMAND cmake -E copy_directory
                     ${CMAKE_CURRENT_SOURCE_DIR}/testdata
                     ${CMAKE_CURRENT_BINARY_DIR}/testdata )
else()
  add_custom_target( copy_testdata_profile
                     COMMAND cmake -E copy_directory
                     ${CMAKE_CURRENT_SOURCE_DIR}/testdata
                     ${CMAKE_CURRENT_BINARY_DIR}/Debug/testdata
                     COMMAND cmake -E copy_directory
                     ${CMAKE_CURRENT_SOURCE_DIR}/testdata
                     ${CMAKE_CURRENT_BINARY_DIR}/Release/testdata )

endif()

add_dependencies( ${PROJECT_NAME} copy_testdata_profile )
