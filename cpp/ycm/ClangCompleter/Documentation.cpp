// Copyright (C) 2015 YouCompleteMe Contributors
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

#include <sstream>

#include "Documentation.h"
#include "ClangHelpers.h"
#include "ClangUtils.h"

#include <clang-c/Documentation.h>

namespace YouCompleteMe {

namespace {

bool CXCommentValid( const CXComment &comment ) {
  return clang_Comment_getKind( comment ) != CXComment_Null;
}

enum BraceKind {
  TOKEN_OPEN_BRACE,
  TOKEN_CLOSE_BRACE,
  TOKEN_NOT_BRACE
};

BraceKind ClassifyToken( const std::string& token_spelling ) {
  if( token_spelling == "{" )
    return TOKEN_OPEN_BRACE;
  else if ( token_spelling == "}" )
    return TOKEN_CLOSE_BRACE;

  return TOKEN_NOT_BRACE;
}

/**
 * Provides RAII for tokenizing a source range.
 */
struct ClangTokenWrap {
  ClangTokenWrap( CXTranslationUnit TU_, const CXSourceRange& range )
    : TU( TU_)
    , tokens( NULL )
    , num_tokens( 0 ) {
    clang_tokenize( TU, range, &tokens, &num_tokens );
  }

  ~ClangTokenWrap() {
    if ( tokens )
      clang_disposeTokens( TU, tokens, num_tokens );
  }

  CXTranslationUnit TU;
  CXToken *tokens;
  unsigned int num_tokens;
};

/**
 * Extract the text of the declaration referenced by cursor from the raw
 * tokens in the source text.
 */
std::string ExtractDeclarationText( CXTranslationUnit TU,
                                    CXCursor cursor ) {

  CXSourceRange range = clang_getCursorReferenceNameRange(
    cursor,
    CXNameRange_WantQualifier |
    CXNameRange_WantTemplateArgs |
    CXNameRange_WantSinglePiece,
    0 /* only one piece due to CXNameRange_WantSinglePiece */ );

  ClangTokenWrap tokens( TU, range );
  std::ostringstream declaration;

  // Print out the text of the declaration in a form that is a useful reference.
  //
  // To do this, we simply scan the tokens of the canonical declaration,
  // printing them. We separate tokens with a single whitespace character,
  // unless in the source text they are adjacent. In particular, this prevents
  // separating token streams like (std)(::)(string) if they are not written
  // that way in the source text. If they are separated in the source text by
  // one or more (non-token) character, we just emit a single whitespace
  // character to help fit the useful information on a single line.
  //
  // Finally we skip all of the contents of elaborated declarations (such as
  // the members of classes/structs and the bodies of functions),
  // but include other qualifiers: we keep track of the "brace depth" and do not
  // print the contents of any top-level brace pair. The effect of this is to
  // print a "terse" version of the elaborated declaration.

  for( unsigned int i           = 0, /* current token index */
                    last_end    = 0, /* byte offset of end of last token */
                    brace_depth = 0; /* nesting level for curly braces */
       tokens.tokens && i < tokens.num_tokens;
       ++i ) {

    bool suppressing_tokens = brace_depth > 0;

    CXSourceRange token_range = clang_getTokenExtent( TU, tokens.tokens[ i ] );

    std::string token_spelling = CXStringToString(
      clang_getTokenSpelling( tokens.TU, tokens.tokens[ i ] ) );

    // For all but the first token, emit a single character of whitespace if
    // this is not a suppressed token (i.e. within a brace) and this token
    // is not adjacent to the previous token in the source text.
    if ( i > 0 ) {
      unsigned int tok_start = 0;
      clang_getFileLocation( clang_getRangeStart( token_range ),
                             NULL /* file */,
                             NULL /* line */,
                             NULL /* column */,
                             &tok_start );

      if (!suppressing_tokens && tok_start > last_end)
        declaration << ' ';
    }

    BraceKind token_kind = ClassifyToken( token_spelling );

    // Squish the contents of elaborated declarations (e.g. structs, classes,
    // etc.) into just "{ }".
    if ( !suppressing_tokens ) {
      declaration << token_spelling;

      if ( token_kind == TOKEN_OPEN_BRACE ) {
        // We're entering a top-level braced section.
        ++brace_depth;
      }
    } else if ( token_kind == TOKEN_OPEN_BRACE ) {
      // We're entering a nth-level braced pair. We just need to keep track
      // so that we can print the correct } and any tokens after it.
      ++brace_depth;
    } else if ( token_kind == TOKEN_CLOSE_BRACE ) {
      --brace_depth;

      if ( brace_depth == 0 ) {
        // We've closed the top-level brace pair. Print this close-brace.
        declaration << token_spelling;
      }
      // Otherwise we've closed a nth-level brace pair.
    }

    // Store the offset of the end of this token to compare with the next one.
    clang_getFileLocation( clang_getRangeEnd( token_range ),
                           NULL /* file */,
                           NULL /* line */,
                           NULL /* column */,
                           &last_end );
  }

  return declaration.str();
}
}

DocumentationData::DocumentationData( CXTranslationUnit TU,
                                      const CXCursor &cursor )
  : raw_comment( CXStringToString( clang_Cursor_getRawCommentText( cursor ) ) )
  , brief_comment( CXStringToString(
                     clang_Cursor_getBriefCommentText( cursor ) ) )
  , canonical_type( CXStringToString(
                      clang_getTypeSpelling( clang_getCursorType( cursor ) ) ) )
  , display_name( CXStringToString( clang_getCursorSpelling( cursor ) ) )
  , declaration_text( ExtractDeclarationText( TU, cursor ) ) {
}

} // namespace YouCompleteMe
