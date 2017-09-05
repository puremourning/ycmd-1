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

from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import division
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

from hamcrest import ( assert_that, contains_inanyorder, empty, has_entries )
from nose.tools import eq_

from pprint import pformat
import requests

from ycmd.tests.java import ( PathToTestFile,
                              IsolatedYcmdInDirectory,
                              WaitUntilCompleterServerReady )
from ycmd.tests.test_utils import ( BuildRequest,
                                    CompletionEntryMatcher )
from ycmd.utils import ReadFile


def _CombineRequest( request, data ):
  return BuildRequest( **_Merge( request, data ) )


def _Merge( request, data ):
  kw = dict( request )
  kw.update( data )
  return kw


def RunTest( app, test ):
  """
  Method to run a simple completion test and verify the result

  test is a dictionary containing:
    'request': kwargs for BuildRequest
    'expect': {
       'response': server response code (e.g. httplib.OK)
       'data': matcher for the server response json
    }
  """

  contents = ReadFile( test[ 'request' ][ 'filepath' ] )

  app.post_json( '/event_notification',
                 _CombineRequest( test[ 'request' ], {
                                  'event_name': 'FileReadyToParse',
                                  'contents': contents,
                                  } ),
                 expect_errors = True )

  # We ignore errors here and we check the response code ourself.
  # This is to allow testing of requests returning errors.
  response = app.post_json( '/completions',
                            _CombineRequest( test[ 'request' ], {
                               'contents': contents
                            } ),
                            expect_errors = True )

  print( 'completer response: {0}'.format( pformat( response.json ) ) )

  eq_( response.status_code, test[ 'expect' ][ 'response' ] )

  assert_that( response.json, test[ 'expect' ][ 'data' ] )


@IsolatedYcmdInDirectory( PathToTestFile( 'simple_eclipse_project' ) )
def GetCompletions_NoQuery_test( app ):
  WaitUntilCompleterServerReady( app )
  RunTest( app, {
    'description': 'semantic completion works for builtin types (no query)',
    'request': {
      'filetype'  : 'java',
      'filepath'  : PathToTestFile( 'simple_eclipse_project',
                                    'src',
                                    'com',
                                    'test',
                                    'TestFactory.java' ),
      'line_num'  : 22,
      'column_num': 12,
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entries( {
        'completions': contains_inanyorder(
          CompletionEntryMatcher( 'equals', 'f' ),
          CompletionEntryMatcher( 'getClass', 'f' ),
          CompletionEntryMatcher( 'hashCode', 'f' ),
          CompletionEntryMatcher( 'notify', 'f' ),
          CompletionEntryMatcher( 'notifyAll', 'f' ),
          CompletionEntryMatcher( 'test', 'm' ),
          CompletionEntryMatcher( 'testString', 'm' ),
          CompletionEntryMatcher( 'wait', 'f', {
            'menu_text': 'wait(long timeout, int nanos) : void',
          } ),
          CompletionEntryMatcher( 'wait', 'f', {
            'menu_text': 'wait(long timeout) : void',
          } ),
          CompletionEntryMatcher( 'wait', 'f', {
            'menu_text': 'wait() : void',
          } ),
        ),
        'errors': empty(),
      } )
    },
  } )
