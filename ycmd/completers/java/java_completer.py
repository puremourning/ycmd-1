# Copyright (C) 2016 ycmd contributors
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
from builtins import *  # noqa
from future import standard_library
standard_library.install_aliases()

import logging
import os
import threading
import time

from subprocess import PIPE

from ycmd import utils

from ycmd.completers.language_server import language_server_completer

_logger = logging.getLogger( __name__ )

LANGUAGE_SERVER_HOME = os.path.join( os.path.dirname( __file__ ),
                                     '..',
                                     '..',
                                     '..',
                                     'third_party',
                                     'java-language-server',
                                     'org.jboss.tools.vscode.product',
                                     'target',
                                     'repository')

# TODO: Java 8 required (validate this)
PATH_TO_JAVA = utils.PathToFirstExistingExecutable( [ 'java' ] )

WORKSPACE_PATH = os.path.join( os.path.dirname( __file__ ),
                               '..',
                               '..',
                               '..',
                               'third_party',
                               'java-language-server',
                               'jdt_ws' )


def ShouldEnableJavaCompleter():
  _logger.info( 'Looking for java lonaguage server' )
  if not PATH_TO_JAVA:
    _logger.warning( "Not enabling java completion: Couldn't find java" )
    return False

  if not os.path.exists( LANGUAGE_SERVER_HOME ):
    _logger.warning( 'Not using java completion: not installed' )
    return False

  # TODO: Check java version

  return True


class JavaCompleter( language_server_completer.LanguageServerCompleter ):
  def __init__( self, user_options):
    super( JavaCompleter, self ).__init__( user_options )

    # Used to ensure that starting/stopping of the server is synchronised
    self._server_state_mutex = threading.RLock()

    with self._server_state_mutex:
      self._server = None
      self._Reset()
      self._StartServer()


  def SupportedFiletypes( self ):
    return [ 'java' ]


  def DebugInfo( self, request_data ):
    if self._ServerIsRunning():
      return 'Server running on stdout: {0}, stdin: {2}'.format(
        self._server_stdout_port,
        self._server_stdin_port )

    return 'Server is not running :('


  def Shutdown( self ):
    self._StopServer()


  def ServerIsHealthy( self, request_data = {} ):
    if not self._ServerIsRunning():
      return False

    return True


  def _Reset( self ):
    self._server_stdin_port = 0
    self._server_stdout_port = 0
    self._server_handle = None

    # TODO: close the sockets in the servre
    self._server = None


  def _StartServer( self ):
    with self._server_state_mutex:
      _logger.info( 'Starting Tern server...' )
      self._server_stdin_port = utils.GetUnusedLocalhostPort()
      self._server_stdout_port = utils.GetUnusedLocalhostPort()

      self._server = language_server_completer.TCPMultiStreamServer(
        self._server_stdin_port,
        self._server_stdout_port )

      self._server.start()

      env = os.environ.copy()
      env[ 'STDIN_PORT' ] = str( self._server_stdin_port )
      env[ 'STDOUT_PORT' ] = str( self._server_stdout_port )

      command = [
        PATH_TO_JAVA,
        '-Declipse.application=org.jboss.tools.vscode.java.id1',
        '-Dosgi.bundles.defaultStartLevel=4',
        '-Declipse.product=org.jboss.tools.vscode.java.product',
        '-Dlog.protocol=true',
        '-Dlog.level=ALL',
        '-jar',
        # TODO: Use a glob like the vscode client does ?
        os.path.abspath ( os.path.join(
          LANGUAGE_SERVER_HOME,
          'plugins',
          'org.eclipse.equinox.launcher_1.4.0.v20160926-1553.jar' ) ),
        '-configuration',
        # TODO: select config for host environment (work out what it does)
        os.path.abspath( os.path.join( LANGUAGE_SERVER_HOME, 'config_mac' ) ),
        '-data',
        # TODO: user option for a workspace path?
        os.path.abspath( WORKSPACE_PATH ),
      ]

      _logger.debug( 'Starting java-server with the following command: '
                    + ' '.join( command ) )

      server_stdout = 'server_stdout'
      server_stderr = 'server_stderr'

      _logger.debug( 'server_stdout: {0}'.format( server_stdout ) )
      _logger.debug( 'server_stderr: {0}'.format( server_stderr ) )

      with utils.OpenForStdHandle( server_stdout ) as stdout:
        with utils.OpenForStdHandle( server_stderr ) as stderr:
          self._server_handle = utils.SafePopen( command,
                                                 stdin = PIPE,
                                                 stdout = stdout,
                                                 stderr = stderr,
                                                 env = env )

      if self._ServerIsRunning():
        _logger.info( 'java-langage-server started, '
                      'with stdin {0}, stdout {1}'.format(
                        self._server_stdin_port,
                        self._server_stdout_port ) )
      else:
        _logger.warning( 'java-language-server failed to start' )
        return

      # Awaiting connection
      # spinlock
      # TODO: timeout
      self._server.TryServerConnection()

      # OK, so now we have to fire the Initialise request to the server:
      #
      # LS PROTOCOL - Initialise request
      #
      # The initialize request is sent as the first request from the client to
      # the server. If the server receives request or notification before the
      # initialize request it should act as follows:
      # - for a request the respond should be errored with code: -32001. The
      #   message can be picked by the server.
      # - notifications should be dropped.
      self._WaitForInitiliase()


  def _StopServer( self ):
    with self._server_state_mutex:
      if self._ServerIsRunning():
        _logger.info( 'Stopping java server with PID {0}'.format(
                          self._server_handle.pid ) )
        self._server_handle.terminate()
        try:
          utils.WaitUntilProcessIsTerminated( self._server_handle,
                                              timeout = 5 )
          _logger.info( 'Tern server stopped' )
        except RuntimeError:
          _logger.exception( 'Error while stopping java server' )

      self._Reset()


  def GetSubcommandsMap( self ):
    return {
      'RestartServer': ( lambda self, request_data, args:
                            self._RestartServer() ),
      'GetType':       (lambda self, request_data, args:
                            self._GetType( request_data ) )
    }


  def _RestartServer( self ):
    with self._server_state_mutex:
      self._StopServer()
      self._StartServer()


  def _ServerIsRunning( self ):
    return utils.ProcessIsRunning( self._server_handle )
