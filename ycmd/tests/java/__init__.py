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

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

import functools
import os
import time

from ycmd import handlers
from ycmd.tests.test_utils import ( ClearCompletionsCache,
                                    CurrentWorkingDirectory,
                                    SetUpApp,
                                    StopCompleterServer,
                                    BuildRequest )
from ycmd.utils import GetCurrentDirectory

shared_app = None
shared_current_dir = None


def PathToTestFile( *args ):
  dir_of_current_script = os.path.dirname( os.path.abspath( __file__ ) )
  return os.path.join( dir_of_current_script, 'testdata', *args )


def setUpPackage():
  """Initializes the ycmd server as a WebTest application that will be shared
  by all tests using the SharedYcmd decorator in this package. Additional
  configuration that is common to these tests, like starting a semantic
  subserver, should be done here."""
  global shared_app, shared_current_dir

  shared_app = SetUpApp()
  shared_current_dir = GetCurrentDirectory()
  os.chdir( PathToTestFile() )
  WaitUntilCompleterServerReady( shared_app )


def tearDownPackage():
  """Cleans up the tests using the SharedYcmd decorator in this package. It is
  executed once after running all the tests in the package."""
  global shared_app, shared_current_dir

  StopCompleterServer( shared_app, 'java' )
  os.chdir( shared_current_dir )


def SharedYcmd( test ):
  """Defines a decorator to be attached to tests of this package. This decorator
  passes the shared ycmd application as a parameter.

  Do NOT attach it to test generators but directly to the yielded tests."""
  global shared_app

  @functools.wraps( test )
  def Wrapper( *args, **kwargs ):
    ClearCompletionsCache()
    return test( shared_app, *args, **kwargs )
  return Wrapper


def IsolatedYcmd( test ):
  """Defines a decorator to be attached to tests of this package. This decorator
  passes a unique ycmd application as a parameter. It should be used on tests
  that change the server state in a irreversible way (ex: a semantic subserver
  is stopped or restarted) or expect a clean state (ex: no semantic subserver
  started, no .ycm_extra_conf.py loaded, etc).

  Do NOT attach it to test generators but directly to the yielded tests."""
  return IsolatedYcmdInDirectory( PathToTestFile() )


def IsolatedYcmdInDirectory( directory ):
  """Defines a decorator to be attached to tests of this package. This decorator
  passes a unique ycmd application as a parameter running in the directory
  supplied. It should be used on tests that change the server state in a
  irreversible way (ex: a semantic subserver is stopped or restarted) or expect
  a clean state (ex: no semantic subserver started, no .ycm_extra_conf.py
  loaded, etc).

  Do NOT attach it to test generators but directly to the yielded tests."""
  def Decorator( test ):
    @functools.wraps( test )
    def Wrapper( *args, **kwargs ):
      old_server_state = handlers._server_state
      app = SetUpApp()
      try:
        with CurrentWorkingDirectory( directory ):
          test( app, *args, **kwargs )
      finally:
        StopCompleterServer( app, 'java' )
        handlers._server_state = old_server_state
    return Wrapper

  return Decorator


def WaitUntilCompleterServerReady( app, timeout = 30 ):
  expiration = time.time() + timeout
  filetype = 'java'
  while True:
    if time.time() > expiration:
      raise RuntimeError( 'Waited for the {0} subserver to be ready for '
                          '{1} seconds, aborting.'.format( filetype, timeout ) )

    if app.get( '/ready', { 'subserver': filetype } ).json:
      return
    else:
      # Poll for messages. The server requires this to handle async messages,
      # and will not become ready without them.
      # FIXME: Is this really what we want? It's tricky to actually handle these
      # things without some trigger.
      app.post_json( '/receive_messages', BuildRequest( **{
        'filetype'  : 'java',
        'filepath'  : PathToTestFile( 'simple_eclipse_project',
                                      'src',
                                      'com',
                                      'test',
                                      'TestFactory.java' ),
        'line_num'  : 15,
        'column_num': 15,
        'contents': ''
      } ) )

    time.sleep( 0.1 )