// Copyright (C) 2017 ycmd contributors.
//
// This file is part of ycmd.
//
// ycmd is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// ycmd is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

#include <iostream>

#include "ClangCompleter.h"
#include "CompletionData.h"
#include "PythonSupport.h"
#include "Result.h"
#include "Candidate.h"
#include "CandidateRepository.h"

#include <vector>

#include <benchmark/benchmark.h>
#include <boost/filesystem.hpp>
#include <boost/algorithm/cxx11/any_of.hpp>
#include <boost/algorithm/string.hpp>

namespace {
  using namespace YouCompleteMe;

  namespace fs = boost::filesystem;
  using boost::algorithm::is_upper;
  using boost::python::len;

  boost::filesystem::path PathToTestFile( const std::string &filepath ) {
    fs::path path_to_testdata = fs::current_path() / fs::path( "testdata" );
    return path_to_testdata / fs::path( filepath );
  }


  void BM_CandidatesForLocationInFile( benchmark::State& state ) {
    ClangCompleter completer;
    while (state.KeepRunning()) {
      std::vector< CompletionData > completions =
        completer.CandidatesForLocationInFile(
          PathToTestFile( "Basic.cpp" ).string(),
          5,
          7,
          std::vector< UnsavedFile >(),
          std::vector< std::string >() );

      if (completions.empty()) {
        state.SkipWithError( "Basic.cpp:5:7 didn't produce any candidates" );
      }
    }
  }

  void BM_FilterAndSortCandidates( benchmark::State& state ) {
    ClangCompleter completer;
    std::vector< CompletionData > completions =
      completer.CandidatesForLocationInFile(
        PathToTestFile( "Basic.cpp" ).string(),
        5,
        7,
        std::vector< UnsavedFile >(),
        std::vector< std::string >() );

    if (completions.empty()) {
      state.SkipWithError( "Basic.cpp:5:7 didn't produce any candidates" );
    }

    int num_candidates = completions.size();
    std::string query = "t";
    std::string candidate_property = "insertion_text";

    while( state.KeepRunning() ) {
      // NOTE: This is a copy/paste of PythonSupport's code to remove all of the
      // boost::python stuff, because it makes the benchmark abort (and I cba to
      // work out why)
      std::vector< std::string > candidate_strings;
      candidate_strings.reserve( num_candidates );

      for ( int i = 0; i < num_candidates; ++i ) {
        if ( candidate_property.empty() ) {
          candidate_strings.push_back(
            completions[ i ].everything_except_return_type_ );
        } else {
          candidate_strings.push_back(
            completions[ i ].everything_except_return_type_ );
        }
      }

      auto repository_candidates =
        CandidateRepository::Instance().GetCandidatesForStrings(
           candidate_strings );
      std::vector< ResultAnd< int > > result_and_objects;
      {
        Bitset query_bitset = LetterBitsetFromString( query );
        bool query_has_uppercase_letters = any_of( query, is_upper() );

        for ( int i = 0; i < num_candidates; ++i ) {
          const Candidate *candidate = repository_candidates[ i ];

          if ( !candidate->MatchesQueryBitset( query_bitset ) )
            continue;

          Result result = candidate->QueryMatchResult(
            query,
            query_has_uppercase_letters );

          if ( result.IsSubsequence() ) {
            ResultAnd< int > result_and_object( result, i );
            result_and_objects.push_back( boost::move( result_and_object ) );
          }
        }

        std::sort( result_and_objects.begin(), result_and_objects.end() );
      }
    }
  }
}

BENCHMARK( BM_CandidatesForLocationInFile )->Unit(
  benchmark::kMicrosecond );
BENCHMARK( BM_FilterAndSortCandidates )->Unit(
  benchmark::kMicrosecond );
