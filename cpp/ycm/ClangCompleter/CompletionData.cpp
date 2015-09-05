// Copyright (C) 2011, 2012  Google Inc.
//
// This file is part of YouCompleteMe.
//
// YouCompleteMe is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// YouCompleteMe is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with YouCompleteMe.  If not, see <http://www.gnu.org/licenses/>.

#include "CompletionData.h"
#include "ClangUtils.h"

#include <boost/regex.hpp>
#include <boost/algorithm/string/erase.hpp>
#include <boost/algorithm/string/predicate.hpp>
#include <boost/move/move.hpp>

namespace YouCompleteMe {

namespace {

CompletionKind CursorKindToCompletionKind( CXCursorKind kind ) {
  switch ( kind ) {
    case CXCursor_StructDecl:
      return STRUCT;

    case CXCursor_ClassDecl:
    case CXCursor_ClassTemplate:
    case CXCursor_ObjCInterfaceDecl:
    case CXCursor_ObjCImplementationDecl:
      return CLASS;

    case CXCursor_EnumDecl:
      return ENUM;

    case CXCursor_UnexposedDecl:
    case CXCursor_UnionDecl:
    case CXCursor_TypedefDecl:
      return TYPE;

    case CXCursor_FieldDecl:
    case CXCursor_ObjCIvarDecl:
    case CXCursor_ObjCPropertyDecl:
    case CXCursor_EnumConstantDecl:
      return MEMBER;

    case CXCursor_FunctionDecl:
    case CXCursor_CXXMethod:
    case CXCursor_FunctionTemplate:
    case CXCursor_ConversionFunction:
    case CXCursor_Constructor:
    case CXCursor_Destructor:
    case CXCursor_ObjCClassMethodDecl:
    case CXCursor_ObjCInstanceMethodDecl:
      return FUNCTION;

    case CXCursor_VarDecl:
      return VARIABLE;

    case CXCursor_MacroDefinition:
      return MACRO;

    case CXCursor_ParmDecl:
      return PARAMETER;

    case CXCursor_Namespace:
    case CXCursor_NamespaceAlias:
      return NAMESPACE;

    default:
      return UNKNOWN;
  }
}


bool IsMainCompletionTextInfo( CXCompletionChunkKind kind ) {
  return
    kind == CXCompletionChunk_Optional         ||
    kind == CXCompletionChunk_TypedText        ||
    kind == CXCompletionChunk_Placeholder      ||
    kind == CXCompletionChunk_CurrentParameter ||
    kind == CXCompletionChunk_Text             ||
    kind == CXCompletionChunk_LeftParen        ||
    kind == CXCompletionChunk_RightParen       ||
    kind == CXCompletionChunk_RightBracket     ||
    kind == CXCompletionChunk_LeftBracket      ||
    kind == CXCompletionChunk_LeftBrace        ||
    kind == CXCompletionChunk_RightBrace       ||
    kind == CXCompletionChunk_RightAngle       ||
    kind == CXCompletionChunk_LeftAngle        ||
    kind == CXCompletionChunk_Comma            ||
    kind == CXCompletionChunk_Colon            ||
    kind == CXCompletionChunk_SemiColon        ||
    kind == CXCompletionChunk_Equal            ||
    kind == CXCompletionChunk_Informative      ||
    kind == CXCompletionChunk_HorizontalSpace;
}


std::string ChunkToString( CXCompletionString completion_string,
                           uint chunk_num ) {
  if ( !completion_string )
    return std::string();

  return YouCompleteMe::CXStringToString(
           clang_getCompletionChunkText( completion_string, chunk_num ) );
}


std::string TrimUnderscores( const std::string &text ) {
  static boost::regex underscores("\\<_+|_+\\>");
  return boost::regex_replace( text, underscores, "" );
}


// foo( -> foo
// foo() -> foo
std::string RemoveTrailingParens( std::string text ) {
  if ( boost::ends_with( text, "(" ) ) {
    boost::erase_tail( text, 1 );
  } else if ( boost::ends_with( text, "()" ) ) {
    boost::erase_tail( text, 2 );
  }

  return text;
}

void AppendChunk( CXCompletionString completion_string,
                  uint chunk_num,
                  std::vector< CompletionData::Chunk >& chunks )
{
  CXCompletionChunkKind kind = clang_getCompletionChunkKind(
                                 completion_string, chunk_num );

  CompletionData::Chunk chunk;

  switch ( kind ) {
    case CXCompletionChunk_Optional:
    {
      CXCompletionString optional_completion_string =
        clang_getCompletionChunkCompletionString( completion_string,
                                                  chunk_num );

      uint optional_num_chunks = clang_getNumCompletionChunks(
                                   optional_completion_string );

      chunk.children.reserve( optional_num_chunks );

      for ( uint j = 0; j < optional_num_chunks; ++j ) {
        AppendChunk( optional_completion_string,
                     j,
                     chunk.children );
      }

      chunk.isOptional = true;
      chunks.push_back( chunk );
      break;
    }

    case CXCompletionChunk_Placeholder:
    case CXCompletionChunk_LeftParen:
    case CXCompletionChunk_RightParen:
    case CXCompletionChunk_LeftBracket:
    case CXCompletionChunk_RightBracket:
    case CXCompletionChunk_LeftBrace:
    case CXCompletionChunk_RightBrace:
    case CXCompletionChunk_LeftAngle:
    case CXCompletionChunk_RightAngle:
    case CXCompletionChunk_Comma:
    case CXCompletionChunk_Colon:
    case CXCompletionChunk_SemiColon:
    case CXCompletionChunk_Equal:
    case CXCompletionChunk_Text:
    case CXCompletionChunk_TypedText:
      chunk.insertion_text = TrimUnderscores( 
                                ChunkToString( completion_string, chunk_num ) );
      chunks.push_back( chunk );
      break;
    // ignored;
    case CXCompletionChunk_Informative:
    case CXCompletionChunk_ResultType:
    case CXCompletionChunk_HorizontalSpace:
    case CXCompletionChunk_VerticalSpace:
    case CXCompletionChunk_CurrentParameter:
      break;
  }
}

} // unnamed namespace


CompletionData::CompletionData( const CXCompletionResult &completion_result,
                                bool is_argument_hint ) {
  CXCompletionString completion_string = completion_result.CompletionString;

  if ( !completion_string )
    return;

  uint num_chunks = clang_getNumCompletionChunks( completion_string );
  bool saw_left_paren = false;
  bool saw_function_params = false;
  bool saw_placeholder = false;

  chunks_.reserve( num_chunks );

  for ( uint j = 0; j < num_chunks; ++j ) {
    ExtractDataFromChunk( completion_string,
                          j,
                          saw_left_paren,
                          saw_function_params,
                          saw_placeholder );
    if ( !is_argument_hint ) {
        AppendChunk( completion_string, j, chunks_ );
    }
  }

  original_string_ = RemoveTrailingParens( boost::move( original_string_ ) );
  kind_ = CursorKindToCompletionKind( completion_result.CursorKind );

  // We trim any underscores from the function definition since identifiers
  // with them are ugly, in most cases compiler-reserved names. Functions
  // from the standard library use parameter names like "__pos" and we want to
  // show them as just "pos". This will never interfere with client code since
  // ANY C++ identifier with two consecutive underscores in it is
  // compiler-reserved.
  everything_except_return_type_ =
    TrimUnderscores( everything_except_return_type_ );

  doc_string_ = YouCompleteMe::CXStringToString(
                  clang_getCompletionBriefComment( completion_string ) );

  if ( !doc_string_.empty() )
    detailed_info_.append( doc_string_ + "\n" );

  detailed_info_.append( return_type_ )
                .append( " " )
                .append( everything_except_return_type_ )
                .append( "\n" );

  if ( is_argument_hint ) {
    kind_ = NONE;
    return_type_ = "";
    original_string_ = "";
    everything_except_return_type_ = TrimUnderscores( current_arg_ );
    if ( everything_except_return_type_.empty() )
      everything_except_return_type_ = "void";
  }
}


std::string
CompletionData::OptionalChunkToString( CXCompletionString completion_string,
                                       uint chunk_num ) {
  std::string final_string;

  if ( !completion_string )
    return final_string;

  CXCompletionString optional_completion_string =
    clang_getCompletionChunkCompletionString( completion_string, chunk_num );

  if ( !optional_completion_string )
    return final_string;

  uint optional_num_chunks = clang_getNumCompletionChunks(
                               optional_completion_string );

  for ( uint j = 0; j < optional_num_chunks; ++j ) {
    CXCompletionChunkKind kind = clang_getCompletionChunkKind(
                                   optional_completion_string, j );

    if ( kind == CXCompletionChunk_Optional ) {
      final_string.append( OptionalChunkToString( optional_completion_string,
                                                  j ) );
    }

    else if ( kind == CXCompletionChunk_Placeholder ) {
      final_string.append(
          "[" + ChunkToString( optional_completion_string, j ) + "]" );
    }

    else if ( kind == CXCompletionChunk_CurrentParameter ) {
      current_arg_ = "[" + ChunkToString( optional_completion_string, j ) + "]";
      final_string.append( "☞  " + current_arg_ );
    }

    else {
      final_string.append( ChunkToString( optional_completion_string, j ) );
    }
  }

  return final_string;
}


void CompletionData::ExtractDataFromChunk( CXCompletionString completion_string,
                                           uint chunk_num,
                                           bool &saw_left_paren,
                                           bool &saw_function_params,
                                           bool &saw_placeholder ) {
  CXCompletionChunkKind kind = clang_getCompletionChunkKind(
                                 completion_string, chunk_num );

  if ( IsMainCompletionTextInfo( kind ) ) {
    if ( kind == CXCompletionChunk_LeftParen ) {
      saw_left_paren = true;
      if ( original_string_.empty() )
        original_string_ = "(*) ";
      if ( everything_except_return_type_.empty() )
        everything_except_return_type_ = "(*) ";
    }

    else if ( saw_left_paren &&
              !saw_function_params &&
              kind != CXCompletionChunk_RightParen &&
              kind != CXCompletionChunk_Informative ) {
      saw_function_params = true;
      everything_except_return_type_.append( " " );
    }

    else if ( saw_function_params && kind == CXCompletionChunk_RightParen ) {
      everything_except_return_type_.append( " " );
    }

    if ( kind == CXCompletionChunk_Optional ) {
      everything_except_return_type_.append(
        OptionalChunkToString( completion_string, chunk_num ) );
    }

    else if ( kind == CXCompletionChunk_CurrentParameter ) {
      current_arg_ = ChunkToString( completion_string, chunk_num );
      everything_except_return_type_.append( "☞  " + current_arg_ );
    }

    else {
      everything_except_return_type_.append(
        ChunkToString( completion_string, chunk_num ) );
    }
  }

  switch ( kind ) {
    case CXCompletionChunk_ResultType:
      return_type_ = ChunkToString( completion_string, chunk_num );
      break;
    case CXCompletionChunk_Placeholder:
    case CXCompletionChunk_CurrentParameter:
      saw_placeholder = true;
      break;
    case CXCompletionChunk_TypedText:
    case CXCompletionChunk_Text:
      // need to add paren to insert string
      // when implementing inherited methods or declared methods in objc.
    case CXCompletionChunk_LeftParen:
    case CXCompletionChunk_RightParen:
    case CXCompletionChunk_HorizontalSpace:
      if ( !saw_placeholder ) {
        original_string_ += ChunkToString( completion_string, chunk_num );
      }
      break;
    default:
      break;
  }
}

} // namespace YouCompleteMe
