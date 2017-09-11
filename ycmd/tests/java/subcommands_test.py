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
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

from hamcrest import assert_that, contains, has_entries
from nose.tools import eq_
import os.path
from pprint import pformat
import requests

from ycmd.utils import ReadFile
from ycmd.tests.java import PathToTestFile, SharedYcmd
from ycmd.tests.test_utils import BuildRequest, ChunkMatcher, ErrorMatcher, LocationMatcher


@SharedYcmd
def Subcommands_DefinedSubcommands_test( app ):
  subcommands_data = BuildRequest( completer_target = 'java' )

  eq_( sorted( [ 'FixIt',
                 'GoToDeclaration',
                 'GoToDefinition',
                 'GoTo',
                 'GetDoc',
                 'GetType',
                 'GoToReferences',
                 'RefactorRename',
                 'RestartServer' ] ),
       app.post_json( '/defined_subcommands',
                      subcommands_data ).json )


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
                                 'filetype': 'java',
                                 } ),
                 expect_errors = True )

  # We also ignore errors here, but then we check the response code
  # ourself. This is to allow testing of requests returning errors.
  response = app.post_json(
    '/run_completer_command',
    CombineRequest( test[ 'request' ], {
      'completer_target': 'filetype_default',
      'contents': contents,
      'filetype': 'java',
      'command_arguments': ( [ test[ 'request' ][ 'command' ] ]
                             + test[ 'request' ].get( 'arguments', [] ) )
    } ),
    expect_errors = True
  )

  print( 'completer response: {0}'.format( pformat( response.json ) ) )

  eq_( response.status_code, test[ 'expect' ][ 'response' ] )

  assert_that( response.json, test[ 'expect' ][ 'data' ] )


@SharedYcmd
def Subcommands_GetDoc_Method_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'AbstractTestWidget.java' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'java',
                             line_num = 17,
                             column_num = 17,
                             contents = contents,
                             command_arguments = [ 'GetDoc' ],
                             completer_target = 'filetype_default' )

  response = app.post_json( '/run_completer_command', event_data ).json

  eq_( response, {
         'message': 'Return runtime debugging info. '
                    'Useful for finding the actual code which is useful.'
  } )


@SharedYcmd
def Subcommands_GetDoc_Class_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'TestWidgetImpl.java' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'java',
                             line_num = 11,
                             column_num = 7,
                             contents = contents,
                             command_arguments = [ 'GetDoc' ],
                             completer_target = 'filetype_default' )

  response = app.post_json( '/run_completer_command', event_data ).json

  eq_( response, {
         'message': 'This is the actual code that matters.'
                    ' This concrete implementation is the equivalent'
                    ' of the main function in other languages'
  } )


@SharedYcmd
def Subcommands_GetType_Class_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'TestWidgetImpl.java' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'java',
                             line_num = 11,
                             column_num = 7,
                             contents = contents,
                             command_arguments = [ 'GetType' ],
                             completer_target = 'filetype_default' )

  response = app.post_json( '/run_completer_command', event_data ).json

  eq_( response, {
         'message': 'com.test.TestWidgetImpl'
  } )

@SharedYcmd
def Subcommands_GetType_Constructor_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'TestWidgetImpl.java' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'java',
                             line_num = 14,
                             column_num = 3,
                             contents = contents,
                             command_arguments = [ 'GetType' ],
                             completer_target = 'filetype_default' )

  response = app.post_json( '/run_completer_command', event_data ).json

  eq_( response, {
         'message': 'com.test.TestWidgetImpl.TestWidgetImpl(String info)'
  } )


@SharedYcmd
def Subcommands_GetType_ClassMemberVariable_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'TestWidgetImpl.java' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'java',
                             line_num = 12,
                             column_num = 18,
                             contents = contents,
                             command_arguments = [ 'GetType' ],
                             completer_target = 'filetype_default' )

  response = app.post_json( '/run_completer_command', event_data ).json

  eq_( response, {
         'message': 'String info'
  } )


@SharedYcmd
def Subcommands_GetType_MethodArgument_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'TestWidgetImpl.java' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'java',
                             line_num = 16,
                             column_num = 17,
                             contents = contents,
                             command_arguments = [ 'GetType' ],
                             completer_target = 'filetype_default' )

  response = app.post_json( '/run_completer_command', event_data ).json

  eq_( response, {
    'message': 'String info - '
                     'com.test.TestWidgetImpl.TestWidgetImpl(String)'
  } )

@SharedYcmd
def Subcommands_GetType_MethodVariable_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'TestWidgetImpl.java' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'java',
                             line_num = 15,
                             column_num = 9,
                             contents = contents,
                             command_arguments = [ 'GetType' ],
                             completer_target = 'filetype_default' )

  response = app.post_json( '/run_completer_command', event_data ).json

  eq_( response, {
         'message': 'int a - '
                    'com.test.TestWidgetImpl.TestWidgetImpl(String)'
  } )


@SharedYcmd
def Subcommands_GetType_Method_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'TestWidgetImpl.java' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'java',
                             line_num = 20,
                             column_num = 15,
                             contents = contents,
                             command_arguments = [ 'GetType' ],
                             completer_target = 'filetype_default' )

  response = app.post_json( '/run_completer_command', event_data ).json

  eq_( response, {
         'message': 'void com.test.TestWidgetImpl.doSomethingVaguelyUseful()'
  } )

# Commented out because of an overlooked corner case
#@SharedYcmd
#def Subcommands_GetType_Class_test( app ):
#  filepath = PathToTestFile( 'simple_eclipse_project',
#                             'src',
#                             'com',
#                             'test',
#                             'TestWidgetImpl.java' )
#  contents = ReadFile( filepath )
#
#  event_data = BuildRequest( filepath = filepath,
#                             filetype = 'java',
#                             line_num = 15,
#                             column_num = 13,
#                             contents = contents,
#                             command_arguments = [ 'GetType' ],
#                             completer_target = 'filetype_default' )
#
#  response = app.post_json( '/run_completer_command', event_data ).json
#
#  eq_( response, {
#    'message': ''
#  } )


@SharedYcmd
def Subcommands_GoToReferences_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'AbstractTestWidget.java' )
  contents = ReadFile( filepath )

  event_data = BuildRequest( filepath = filepath,
                             filetype = 'java',
                             line_num = 10,
                             column_num = 15,
                             contents = contents,
                             command_arguments = [ 'GoToReferences' ],
                             completer_target = 'filetype_default' )

  response = app.post_json( '/run_completer_command', event_data ).json

  eq_( response, [
         {
           'filepath': PathToTestFile( 'simple_eclipse_project',
                                       'src',
                                       'com',
                                       'test',
                                       'TestFactory.java' ),
           'column_num': 9,
           # 'description': '',
           'line_num': 23
         },
         {
           'filepath': PathToTestFile( 'simple_eclipse_project',
                                       'src',
                                       'com',
                                       'test',
                                       'TestLauncher.java' ),
           'column_num': 7,
           # 'description': '',
           'line_num': 8
         } ] )


@SharedYcmd
def Subcommands_RefactorRename_Simple_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'TestLauncher.java' )
  RunTest( app, {
    'description': 'RefactorRename works within a single scope/file',
    'request': {
      'command': 'RefactorRename',
      'arguments': [ 'renamed_l' ],
      'filepath': filepath,
      'line_num': 15,
      'column_num': 5,
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entries ( {
        'fixits': contains( has_entries( {
          'chunks': contains(
              ChunkMatcher( 'renamed_l',
                            LocationMatcher( filepath, 14, 18 ),
                            LocationMatcher( filepath, 14, 19 ) ),
              ChunkMatcher( 'renamed_l',
                            LocationMatcher( filepath, 15, 5 ),
                            LocationMatcher( filepath, 15, 6 ) ),
          ),
          'location': LocationMatcher( filepath, 15, 5 )
        } ) )
      } )
    }
  } )


@SharedYcmd
def Subcommands_RefactorRename_MultipleFiles_test( app ):
  filepath1 = PathToTestFile( 'simple_eclipse_project',
                              'src',
                              'com',
                              'test',
                              'AbstractTestWidget.java' )
  filepath2 = PathToTestFile( 'simple_eclipse_project',
                              'src',
                              'com',
                              'test',
                              'TestFactory.java' )
  filepath3 = PathToTestFile( 'simple_eclipse_project',
                              'src',
                              'com',
                              'test',
                              'TestLauncher.java' )
  filepath4 = PathToTestFile( 'simple_eclipse_project',
                              'src',
                              'com',
                              'test',
                              'TestWidgetImpl.java' )

  RunTest( app, {
    'description': 'RefactorRename works across files',
    'request': {
      'command': 'RefactorRename',
      'arguments': [ 'a-quite-long-string' ],
      'filepath': filepath3,
      'line_num': 8,
      'column_num': 7,
    },
    'expect': {
      'response': requests.codes.ok,
      'data': has_entries ( {
        'fixits': contains( has_entries( {
          'chunks': contains(
            ChunkMatcher(
              'a-quite-long-string',
              LocationMatcher( filepath1, 10, 15 ),
              LocationMatcher( filepath1, 10, 39 ) ),
            ChunkMatcher(
              'a-quite-long-string',
              LocationMatcher( filepath2, 23, 9 ),
              LocationMatcher( filepath2, 23, 33 ) ),
            ChunkMatcher(
              'a-quite-long-string',
              LocationMatcher( filepath4, 20, 15 ),
              LocationMatcher( filepath4, 20, 39 ) ),
            ChunkMatcher(
              'a-quite-long-string',
              LocationMatcher( filepath3, 8, 7 ),
              LocationMatcher( filepath3, 8, 31 ) )
          ),
          'location': LocationMatcher( filepath3, 8, 7 )
        } ) )
      } )
    }
  } )


@SharedYcmd
def Subcommands_RefactorRename_Missing_New_Name_test( app ):
  filepath = PathToTestFile( 'simple_eclipse_project',
                             'src',
                             'com',
                             'test',
                             'TestLauncher.java' )
  RunTest( app, {
    'description': 'RefactorRename raises an error without new name',
    'request': {
      'command': 'RefactorRename',
      'line_num': 15,
      'column_num': 5,
      'filepath': filepath,
    },
    'expect': {
      'response': requests.codes.internal_server_error,
      'data': ErrorMatcher( ValueError,
                            'Please specify a new name to rename it to.\n'
                            'Usage: RefactorRename <new name>' ),
    }
  } )
