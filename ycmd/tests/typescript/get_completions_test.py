# Copyright (C) 2015 ycmd contributors
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

from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import json
from hamcrest import assert_that, contains_inanyorder, has_entries
from mock import patch

from ycmd.tests.typescript import PathToTestFile, SharedYcmd
from ycmd.tests.test_utils import BuildRequest, CompletionEntryMatcher
from ycmd.utils import ReadFile


def RunTest( app, test ):
  filepath = PathToTestFile( 'test.ts' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'typescript',
                             contents = contents,
                             event_name = 'BufferVisit' )

  app.post_json( '/event_notification', event_data )

  completion_data = BuildRequest(
      filepath = filepath,
      filetype = 'typescript',
      contents = contents,
      force_semantic = True,
      line_num = test[ 'request' ][ 'line_num' ],
      column_num = test[ 'request' ][ 'column_num' ] )

  response = app.post_json( '/completions', completion_data ).json

  print( json.dumps( response, indent=2 ) )

  assert_that( response, test[ 'expect' ][ 'data' ] )


@SharedYcmd
def GetCompletions_Basic_test( app ):
  RunTest( app, {
    'request' : {
      'line_num': 17,
      'column_num': 6,
    },
    'expect': {
      'data': has_entries( {
        'completions': contains_inanyorder(
          CompletionEntryMatcher( 'methodA', extra_params = {
            'extra_menu_info': '(method) Foo.methodA(): void',
            'detailed_info': '(method) Foo.methodA(): void',
          } ),
          CompletionEntryMatcher( 'methodB', extra_params = {
            'extra_menu_info': '(method) Foo.methodB(): void',
            'detailed_info': '(method) Foo.methodB(): void'
          } ),
          CompletionEntryMatcher( 'methodC', extra_params = {
            'extra_menu_info': ( '(method) Foo.methodC(a: '
                                 '{ foo: string; bar: number; }): void' ),
            'detailed_info': ( '(method) Foo.methodC(a: '
                               '{ foo: string; bar: number; }): void' )
          } ),
        )
      } )
    }
  } )


@SharedYcmd
def GetCompletions_WithDocs_test( app ):
  RunTest( app, {
    'request' : {
      'line_num': 39,
      'column_num': 5,
    },
    'expect': {
      'data': has_entries( {
        'completions': contains_inanyorder(
          CompletionEntryMatcher( 'testMethod', extra_params = {
            'extra_menu_info': '(method) Bar.testMethod(): void',
            'detailed_info': ( '(method) Bar.testMethod(): void\n'
                                'Method documentation' ),
          } ),
          CompletionEntryMatcher( 'member', extra_params = {
            'extra_menu_info': '(property) Bar.member: string',
            'detailed_info': ( '(property) Bar.member: string\n'
                                'Variable documentation' ),
          } )
        )
      } )
    }
  } )


@SharedYcmd
@patch( 'ycmd.completers.typescript.'
          'typescript_completer.MAX_DETAILED_COMPLETIONS',
        2 )
def GetCompletions_MaxDetailedCompletion_test( app ):
  RunTest( app, {
    'request' : {
      'line_num': 17,
      'column_num': 6,
    },
    'expect': {
      'data': has_entries( {
        'completions': contains_inanyorder(
          CompletionEntryMatcher( 'methodA' ),
          CompletionEntryMatcher( 'methodB' ),
          CompletionEntryMatcher( 'methodC' )
        )
      } )
    }
  } )
