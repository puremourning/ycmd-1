# Copyright (C) 2015-2019 ycmd contributors
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
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

from hamcrest import ( assert_that,
                       contains,
                       contains_inanyorder,
                       contains_string,
                       equal_to,
                       has_entry )
from mock import patch
from pprint import pformat
import os
import requests

from ycmd import handlers
from ycmd.tests.swift import PathToTestFile, SharedYcmd
from ycmd.tests.test_utils import ( BuildRequest,
                                    ErrorMatcher,
                                    LocationMatcher,
                                    UnixOnly )
from ycmd.utils import ReadFile


def RunTest( app, test, contents = None ):
  if not contents:
    contents = ReadFile( test[ 'request' ][ 'filepath' ] )

  def CombineRequest( request, data ):
    kw = request
    request.update( data )
    return BuildRequest( **kw )

  # Because we aren't testing this command, we *always* ignore errors. This
  # is mainly because we (may) want to test scenarios where the completer
  # throws an exception and the easiest way to do that is to throw from
  # within the FlagsForFile function.
  app.post_json( '/event_notification',
                 CombineRequest( test[ 'request' ], {
                                 'event_name': 'FileReadyToParse',
                                 'contents': contents,
                                 'filetype': 'swift',
                                 } ),
                 expect_errors = True )

  # We also ignore errors here, but then we check the response code
  # ourself. This is to allow testing of requests returning errors.
  response = app.post_json(
    '/run_completer_command',
    CombineRequest( test[ 'request' ], {
      'completer_target': 'filetype_default',
      'contents': contents,
      'filetype': 'swift',
      'command_arguments': ( [ test[ 'request' ][ 'command' ] ]
                             + test[ 'request' ].get( 'arguments', [] ) )
    } ),
    expect_errors = True
  )

  print( 'completer response: {}'.format( pformat( response.json ) ) )

  assert_that( response.status_code,
               equal_to( test[ 'expect' ][ 'response' ] ) )
  assert_that( response.json, test[ 'expect' ][ 'data' ] )


@UnixOnly
@SharedYcmd
def Subcommands_DefinedSubcommands_test( app ):
  subcommands_data = BuildRequest( completer_target = 'swift' )

  assert_that( app.post_json( '/defined_subcommands', subcommands_data ).json,
               contains_inanyorder( 'ExecuteCommand',
                                    'GetDoc',
                                    'GetType',
                                    'GoTo',
                                    'GoToDeclaration',
                                    'GoToDefinition',
                                    'GoToImplementation',
                                    'GoToReferences',
                                    'RestartServer' ) )


@UnixOnly
def Subcommands_ServerNotInitialized_test():
  filepath = PathToTestFile( 'Sources', 'test', 'main.swift' )

  completer = handlers._server_state.GetFiletypeCompleter( [ 'swift' ] )

  @SharedYcmd
  @patch.object( completer, '_ServerIsInitialized', return_value = False )
  def Test( app, cmd, arguments, *args ):
    RunTest( app, {
      'description': 'Subcommand ' + cmd + ' handles server not ready',
      'request': {
        'command': cmd,
        'line_num': 1,
        'column_num': 1,
        'filepath': filepath,
        'arguments': arguments,
      },
      'expect': {
        'response': requests.codes.internal_server_error,
        'data': ErrorMatcher( RuntimeError,
                              'Server is initializing. Please wait.' ),
      }
    } )

  yield Test, 'GetType', []
  yield Test, 'GetDoc', []
  yield Test, 'GoTo', []
  yield Test, 'GoToDeclaration', []
  yield Test, 'GoToDefinition', []
  yield Test, 'GoToImplementation', []
  yield Test, 'GoToReferences', []


@UnixOnly
@SharedYcmd
def Subcommands_GetDoc_NoDocumentation_test( app ):
  RunTest( app, {
    'description': 'GetDoc on a function with no documentation '
                   'raises an error',
    'request': {
      'command': 'GetDoc',
      'line_num': 3,
      'column_num': 1,
      'filepath': PathToTestFile( 'Sources', 'test', 'main.swift' ),
    },
    'expect': {
      'response': requests.codes.internal_server_error,
      'data': ErrorMatcher(
        RuntimeError, 'No hover information.' )
    }
  } )


@UnixOnly
@SharedYcmd
def Subcommands_GetDoc_Function_test( app ):
  RunTest( app, {
    'description': 'GetDoc on a function returns its documentation',
    'request': {
      'command': 'GetDoc',
      'line_num': 1,
      'column_num': 1,
      'filepath': PathToTestFile( 'Sources', 'test', 'main.swift' ),
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entry( 'detailed_info', contains_string(
        'Writes the textual representations of the given items'
        ' into the standard output.' ) ),
    }
  } )


@UnixOnly
@SharedYcmd
def Subcommands_GetType_UnknownType_test( app ):
  RunTest( app, {
    'description': 'GetType on a unknown type raises an error',
    'request': {
      'command': 'GetType',
      'line_num': 3,
      'column_num': 1,
      'filepath': PathToTestFile( 'Sources', 'test', 'main.swift' ),
    },
    'expect': {
      'response': requests.codes.internal_server_error,
      'data': ErrorMatcher( RuntimeError, 'No hover information.' )
    }
  } )


@UnixOnly
@SharedYcmd
def Subcommands_GetType_Function_test( app ):
  RunTest( app, {
    'description': 'GetType on a function returns its type',
    'request': {
      'command': 'GetType',
      'line_num': 1,
      'column_num': 1,
      'filepath': PathToTestFile( 'Sources', 'test', 'main.swift' ),
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entry( 'detailed_info',
        'func print(_ items: Any..., separator: String = " ",'
        ' terminator: String = "\\n")' ),
    }
  } )


@UnixOnly
@SharedYcmd
def RunGoToTest( app, command, test ):
  folder = PathToTestFile( 'Sources', 'test' )
  filepath = os.path.join( folder, 'main.swift' )
  request = {
    'command': command,
    'line_num': test[ 'req' ][ 0 ],
    'column_num': test[ 'req' ][ 1 ],
    'filepath': filepath,
  }

  response = test[ 'res' ]

  if isinstance( response, list ):
    expect = {
      'response': requests.codes.ok,
      'data': contains( *[
        LocationMatcher(
          os.path.join( folder, location[ 0 ] ),
          location[ 1 ],
          location[ 2 ]
        ) for location in response
      ] )
    }
  elif isinstance( response, tuple ):
    expect = {
      'response': requests.codes.ok,
      'data': LocationMatcher(
        os.path.join( folder, filepath ),
        response[ 0 ],
        response[ 1 ]
      )
    }
  else:
    error_type = test.get( 'exc', RuntimeError )
    expect = {
      'response': requests.codes.internal_server_error,
      'data': ErrorMatcher( error_type, test[ 'res' ] )
    }

  RunTest( app, {
    'request': request,
    'expect' : expect
  } )


def Subcommands_GoTo_test():
  tests = [
    # Standard function
    { 'req': ( 1, 14 ), 'res': 'Cannot jump to location' },
    # Implementation
    { 'req': ( 3,  9 ), 'res': ( 2, 5 ) },
    # Keyword
    { 'req': ( 3,  2 ), 'res': 'Cannot jump to location' },
  ]

  for test in tests:
    for command in [ 'GoToDeclaration', 'GoToDefinition', 'GoTo' ]:
      yield RunGoToTest, command, test
