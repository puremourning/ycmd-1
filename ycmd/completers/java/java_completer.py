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
import socket
import time

from subprocess import PIPE

from ycmd.completers.completer import Completer
from ycmd import utils
from ycmd.completers.java import lsapi

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


class Server( threading.Thread ):
  """Encapsulates communication with the server, which is necessarily
  asyncronous. The server requires that the client open and listen on the ports
  (presumably to eliminate the race condition), and is able to send both
  solicited replies and unsolicited messages to the client asyncronously.
  Indeed, for now clear reason, the general approach is independent 'input' and
  'output' sockets"""
  def __init__( self, input_port, output_port ):
    super( Server, self ).__init__()

    self._input_port = input_port
    self._input_socket = socket.socket( socket.AF_INET, socket.SOCK_STREAM )

    self._output_port = output_port
    self._output_socket = socket.socket( socket.AF_INET, socket.SOCK_STREAM )

    self._client_read_socket = None
    self._client_write_socket = None

    self.input_connected = False
    self.output_connected = False


  def run( self ):
    self._input_socket.bind( ( 'localhost', self._input_port ) )
    self._input_socket.listen( 0 )

    self._output_socket.bind( ( 'localhost', self._output_port ) )
    self._output_socket.listen( 0 )

    tries = 10
    while tries > 0 and not self._TryServerConnectionBlocking():
      _logger.debug( "Server hasn't connected: {0} tries remaining".format(
        tries ) )
    tries -= 1


  def TryServerConnection( self ):
    return self.input_connected and self.output_connected


  def _TryServerConnectionBlocking( self ):
    ( self._client_read_socket, _ ) = self._input_socket.accept()
    self.input_connected = True
    _logger.info( 'Input socket connected' )

    ( self._client_write_socket, _ ) = self._output_socket.accept()
    self.output_connected = True
    _logger.info( 'Output socket connected' )

    return True


  def Write( self, data ):
    assert self.output_connected
    assert self._client_write_socket

    total_sent = 0
    while total_sent < len( data ):
      sent = self._client_write_socket.send( data[ total_sent: ] )
      if sent == 0:
        raise RuntimeError( 'write socket failed' )

      total_sent += sent

    _logger.debug( 'Write complete' )


  def Read( self, size=-1 ):
    # From now on we will only read from self._client_read_socket and write to
    # _client_write_socket
    if size < 0:
      data = self._client_read_socket.recv( 2048 )
      if data == '':
        raise RuntimeError( 'read socket failed' )

      return data

    chunks = []
    bytes_read = 0
    while bytes_read < size:
      chunk = self._client_read_socket.recv( min( size - bytes_read , 2048 ) )
      if chunk == '':
        raise RuntimeError( 'read socket failed' )

      chunks.append( chunk )
      bytes_read += len( chunk )

    return utils.ToBytes( '' ).join( chunks )



class JavaCompleter( Completer ):
  def __init__( self, user_options):
    super( JavaCompleter, self ).__init__( user_options )

    # Used to ensure that starting/stopping of the server is synchronised
    self._server_state_mutex = threading.RLock()

    with self._server_state_mutex:
      self._server = None
      self._Reset()
      self._StartServer()


  def ComputeCandidatesInner( self, request_data ):
    pass


  def OnFileReadyToParse( self, request_data ):
    pass


  # The remainder is all server state handling and completer boilerplate

  def GetSubcommandsMap( self ):
    return {
      'RestartServer': ( lambda self, request_data, args:
                            self._RestartServer() ),
    }


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

      self._server = Server( self._server_stdin_port,
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
      while not self._server.TryServerConnection():
        _logger.debug( 'Awaiting connection on ports: IN {0}, OUT {1}'.format(
          self._server_stdin_port, self._server_stdout_port ) )
        time.sleep( 1 )

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

      self._response = dict()
      self._notification = list()
      self._WaitForInitiliase()


  def _WaitForInitiliase( self ):
    # TODO: Race conditions!
    request_id = len( self._response )

    msg = lsapi.Initialise( request_id )
    _logger.info( 'Sending initialise request to server: {0}'.format( msg ) )
    self._server.Write( msg )
    while request_id not in self._response:
      self._ReadMessage()

    response = self._response[ request_id ]
    del self._response[ request_id ]

    _logger.info( 'Got a response to initialise: {0}'.format( response ) )


  def _ReadMessage( self ):
    # TODO: This like 100% needs to be thread-safe. Currently it is not and that
    # is totally busted).
    # Reading messages should be entirely done in another thread (in
    # real-time) and the "response" and "notification" objects should be
    # synchronised queues. Then the handler threads just send messages and
    # sleep until stuff is put in those queues. Any handler doing any work
    # handles the notifications.
    # This was the original intention, but it took a while to make the code even
    # work, so compression should come later
    headers = {}
    headers_complete = False
    while not headers_complete:
      read_bytes = 0
      last_line = 0
      data = self._server.Read()
      _logger.debug( 'Read data: {0}'.format( data ) )

      while read_bytes < len( data ):
        if data[ read_bytes ] == bytes( b'\n' ):
          line = data[ last_line : read_bytes ].strip()
          _logger.debug( 'Read line: {0}'.format( line ) )
          last_line = read_bytes

          if not line:
            headers_complete = True
            read_bytes += 1
            break
          else:
            key, value = utils.ToUnicode( line ).split( ':', 1 )
            headers[ key.strip() ] = value.strip()

        read_bytes += 1

    # The response message is a JSON object which comes back on one line.
    # Since this might change in the future, we use the 'Content-Length'
    # header.
    if 'Content-Length' not in headers:
      raise RuntimeError( "Missing 'Content-Length' header" )
    content_length = int( headers[ 'Content-Length' ] )

    _logger.debug( 'Need to read {0} bytes of content'.format(
      content_length ) )

    content = bytes( b'' )
    content_read = 0
    if read_bytes < len( data ):
      data = data[ read_bytes: ]
      content_to_read = min( content_length - content_read, len( data ) )
      content += data[ : content_to_read ]
      content_read += len( content )

    while content_read < content_length:
      data = self._server.Read( content_length - content_read )
      content_to_read = min( content_length - content_read, len( data ) )
      content += data[ : content_to_read ]
      content_read += len( content )

    message = lsapi.Parse( content )
    self._DespatchMessage( message )


  def _DespatchMessage( self, message ):
    _logger.debug( 'Received message: {0}'.format( message ) )
    if 'id' in message:
      self._response[ message[ 'id' ] ] = message
    else:
      # TODO: how to handle notifications
      self._notification.append( message )


  def _StopServer( self ):
    with self._server_state_mutex:
      if self._ServerIsRunning():
        self._server_handle.terminate()
        try:
          utils.WaitUntilProcessIsTerminated( self._server_handle,
                                              timeout = 5 )
        except RuntimeError:
          _logger.exception( 'Error while stopping java server' )

      self._Reset()


  def _RestartServer( self ):
    with self._server_state_mutex:
      self._StopServer()
      self._StartServer()


  def _ServerIsRunning( self ):
    return utils.ProcessIsRunning( self._server_handle )
