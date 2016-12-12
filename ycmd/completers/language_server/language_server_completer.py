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
import threading
import socket
import json
import os

from ycmd.completers.completer import Completer
from ycmd import utils
from ycmd.completers.java import lsapi
from ycmd import responses

_logger = logging.getLogger( __name__ )


class TCPSingleStreamServer( threading.Thread ):
  def __init__( self, port ):
    super( TCPSingleStreamServer, self ).__init__()

    self._port = port
    self._socket = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
    self._client_socket = None
    self.client_connected = False


  def run( self ):
    self._socket.bind( ( 'localhost', self._port ) )
    self._socket.listen( 0 )

    tries = 10
    while tries > 0 and not self._TryServerConnectionBlocking():
      _logger.debug( "Server hasn't connected: {0} tries remaining".format(
        tries ) )
    tries -= 1


  def TryServerConnection( self ):
    return self.client_connected


  def _TryServerConnectionBlocking( self ):
    ( self._client_socket, _ ) = self._socket.accept()
    self.client_connected = True
    _logger.info( 'socket connected' )

    return True


  def Write( self, data ):
    assert self.client_connected
    assert self._client_socket

    total_sent = 0
    while total_sent < len( data ):
      sent = self._client_socket.send( data[ total_sent: ] )
      if sent == 0:
        raise RuntimeError( 'write socket failed' )

      total_sent += sent

    _logger.debug( 'Write complete' )


  def Read( self, size=-1 ):
    assert self.client_connected
    assert self._client_socket

    if size < 0:
      data = self._client_socket.recv( 2048 )
      if data == '':
        raise RuntimeError( 'read socket failed' )

      return data

    chunks = []
    bytes_read = 0
    while bytes_read < size:
      chunk = self._client_socket.recv( min( size - bytes_read , 2048 ) )
      if chunk == '':
        raise RuntimeError( 'read socket failed' )

      chunks.append( chunk )
      bytes_read += len( chunk )

    return utils.ToBytes( '' ).join( chunks )


class TCPMultiStreamServer( threading.Thread ):
  def __init__( self, input_port, output_port ):
    super( TCPMultiStreamServer, self ).__init__()

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
    assert self.input_connected
    assert self._client_read_socket

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



class LanguageServerCompleter( Completer ):
  def __init__( self, user_options):
    super( LanguageServerCompleter, self ).__init__( user_options )
    self._notification = list()
    self._response = dict()


  def ComputeCandidatesInner( self, request_data ):

    # Need to update the file contents. TODO: so inefficient!
    self._RefreshFiles( request_data )

    # TODO: Must absolutely FIX the race conditions here!!!
    request_id = str ( len( self._response ) )

    msg = lsapi.Completion( request_id, request_data )
    _logger.info( 'Sending completion request to server: {0}'.format( msg ) )
    self._server.Write( msg )

    # TODO: AAAAH so broken threading....
    while request_id not in self._response:
      self._ReadMessage()

    # TODO: AAAAAAH race conditions
    response = self._response[ request_id ]
    del self._response[ request_id ]

    _logger.info( 'Got a response to completion: {0}'.format(
      json.dumps( response, indent=2 ) ) )

    def Falsy( key, item ):
      return key not in item or not item[ 'key' ]

    def MakeCompletion( item ):
      ITEM_KIND = [
        None,  # 1-based
        'Text',
        'Method',
        'Function',
        'Constructor',
        'Field',
        'Variable',
        'Class',
        'Interface',
        'Module',
        'Property',
        'Unit',
        'Value',
        'Enum',
        'Keyword',
        'Snippet',
        'Color',
        'File',
        'Reference',
      ]

      if 'textEdit' in item and item[ 'textEdit' ]:
        # TODO: This is a very annoying way to supply completions, but YCM could
        # technically support it via FixIt
        insertion_text = item[ 'textEdit' ][ 'newText' ]
      elif 'insertText' in item and item[ 'insertText' ]:
        insertion_text = item[ 'insertText' ]
      else:
        insertion_text = item[ 'label' ]

      return responses.BuildCompletionData(
        insertion_text,
        None,
        None,
        item[ 'label' ],
        ITEM_KIND[ item[ 'kind' ] ],
        None )

    return [ MakeCompletion( i ) for i in response[ 'result' ][ 'items' ] ]


  def OnFileReadyToParse( self, request_data ):
    # TODO: Maintain state about opened, closed etc. files?
    self._RefreshFiles( request_data )


  def _RefreshFiles( self, request_data ):
    for file_name, file_data in request_data[ 'file_data' ].iteritems():
      msg = lsapi.DidOpenTextDocument( file_name,
                                       file_data[ 'filetypes' ],
                                       file_data[ 'contents' ] )
      _logger.info( 'Sending did open request to server: {0}'.format( msg ) )
      self._server.Write( msg )


  # The remainder is all server state handling and completer boilerplate

  def GetSubcommandsMap( self ):
    return {
      'RestartServer': ( lambda self, request_data, args:
                            self._RestartServer() ),
    }


  def _WaitForInitiliase( self ):
    # TODO: Race conditions!
    request_id = str ( len( self._response ) )

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
    prefix = bytes( b'' )
    while not headers_complete:
      read_bytes = 0
      last_line = 0
      data = self._server.Read()
      _logger.debug( 'Read data: {0}'.format( data ) )

      while read_bytes < len( data ):
        if data[ read_bytes ] == bytes( b'\n' ):
          line = prefix + data[ last_line : read_bytes ].strip()
          prefix = ''
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

      if not headers_complete:
        prefix = data[ last_line : ]

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
      self._response[ str( message[ 'id' ] ) ] = message
    else:
      # TODO: how to handle notifications
      self._notification.append( message )
