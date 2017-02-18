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
import queue

from ycmd.completers.completer import Completer
from ycmd import utils
from ycmd import responses

from ycmd.completers.language_server import lsapi

_logger = logging.getLogger( __name__ )


class Response( object ):
  def __init__( self ):
    self._event = threading.Event()
    self._message = None


  def ResponseReceived( self, message ):
    self._message = message
    self._event.set()


  def AwaitResponse( self ):
    self._event.wait( timeout = 5 )

    if not self._event.isSet():
      raise RuntimeError( 'Response Timeout' )

    if 'error' in self._message:
      raise RuntimeError( 'Request failed: {0}'.format(
        self._message[ 'error' ][ 'message' ] ) )

    return self._message


class LanguageServerConnection( object ):
  def __init__( self ):
    super( LanguageServerConnection, self ).__init__()

    self._lastId = 0
    self._responses = {}
    self._responseMutex = threading.Lock()
    self._notifications = queue.Queue()
    self._diagnostics = queue.Queue()

    self._connection_event = threading.Event()


  def NextRequestId( self ):
    with self._responseMutex:
      self._lastId += 1
      return str( self._lastId )


  def GetResponse( self, request_id, message ):
    response = Response()

    with self._responseMutex:
      assert request_id not in self._responses
      self._responses[ request_id ] = response

    self._Write( message )
    return response.AwaitResponse()


  def SendNotification( self, message ):
    self._Write( message )


  def TryServerConnection( self ):
    self._connection_event.wait( timeout = 10 )

    if not self._connection_event.isSet():
      raise RuntimeError( 'Timed out waiting for server to connect' )


  def _run_loop( self, socket ):
    # Wait for the connection to fully establsh (block)
    self._TryServerConnectionBlocking()

    self._connection_event.set()

    # Blocking loop which reads whole messages and calls _DespatchMessage
    self._ReadMessages( )


  def _ReadHeaders( self, data ):
    headers_complete = False
    prefix = bytes( b'' )
    headers = {}

    while not headers_complete:
      read_bytes = 0
      last_line = 0
      if len( data ) == 0:
        data = self.Read()

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
        data = ''


    return ( data, read_bytes, headers )


  def _ReadMessages( self ):
    data = bytes( b'' )
    while True:
      ( data, read_bytes, headers ) = self._ReadHeaders( data )

      if 'Content-Length' not in headers:
        raise RuntimeError( "Missing 'Content-Length' header" )

      content_length = int( headers[ 'Content-Length' ] )

      _logger.debug( 'Need to read {0} bytes of content'.format(
        content_length ) )

      # We need to read content_length bytes for the payload of this message.
      # This may be in the remainder of `data`, but equally we may need to read
      # more data from the socket.
      content = bytes( b'' )
      content_read = 0
      if read_bytes < len( data ):
        # There are bytes left in data, use them
        data = data[ read_bytes: ]

        # Read up to content_length bytes from data
        content_to_read = min( content_length, len( data ) )
        content += data[ : content_to_read ]
        content_read += len( content )
        read_bytes = content_to_read

      while content_read < content_length:
        # There is more content to read, but data is exhausted - read more from
        # the socket
        data = self.Read( content_length - content_read )
        content_to_read = min( content_length - content_read, len( data ) )
        content += data[ : content_to_read ]
        content_read += len( content )
        read_bytes = content_to_read

      self._DespatchMessage( lsapi.Parse( content ) )

      # We only consumed len( content ) of data. If there is more, we start
      # again with the remainder and look for headers
      data = data[ read_bytes : ]


  def _DespatchMessage( self, message ):
    _logger.debug( 'Received message: {0}'.format( message ) )
    if 'id' in message:
      with self._responseMutex:
        assert str( message[ 'id' ] ) in self._responses
        self._responses[ str( message[ 'id' ] ) ].ResponseReceived( message )
    elif message[ 'method' ] == 'textDocument/publishDiagnostics':
      # HACK: We use different mechanisms to publish diagnostics and other
      # async. events (for now)
      self._diagnostics.put( message )
    else:
      self._notifications.put( message )


class TCPSingleStreamServer( LanguageServerConnection, threading.Thread ):
  def __init__( self, port ):
    super( TCPSingleStreamServer, self ).__init__()

    self._port = port
    self._socket = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
    self._client_socket = None


  def run( self ):
    self._socket.bind( ( 'localhost', self._port ) )
    self._socket.listen( 0 )

    self._run_loop( self._client_socket )


  def _TryServerConnectionBlocking( self ):
    ( self._client_socket, _ ) = self._socket.accept()
    _logger.info( 'socket connected' )

    return True


  def _Write( self, data ):
    assert self._connection_event.isSet()
    assert self._client_socket

    total_sent = 0
    while total_sent < len( data ):
      sent = self._client_socket.send( data[ total_sent: ] )
      if sent == 0:
        raise RuntimeError( 'write socket failed' )

      total_sent += sent

    _logger.debug( 'Write complete' )


  def Read( self, size=-1 ):
    assert self._connection_event.isSet()
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


class TCPMultiStreamServer( LanguageServerConnection, threading.Thread ):
  def __init__( self, input_port, output_port ):
    super( TCPMultiStreamServer, self ).__init__()

    self._connection_event = threading.Event()

    self._input_port = input_port
    self._input_socket = socket.socket( socket.AF_INET, socket.SOCK_STREAM )

    self._output_port = output_port
    self._output_socket = socket.socket( socket.AF_INET, socket.SOCK_STREAM )

    self._client_read_socket = None
    self._client_write_socket = None


  def run( self ):
    self._input_socket.bind( ( 'localhost', self._input_port ) )
    self._input_socket.listen( 0 )

    self._output_socket.bind( ( 'localhost', self._output_port ) )
    self._output_socket.listen( 0 )

    self._run_loop( self._client_read_socket )


  def _TryServerConnectionBlocking( self ):
    ( self._client_read_socket, _ ) = self._input_socket.accept()
    _logger.info( 'Input socket connected' )

    ( self._client_write_socket, _ ) = self._output_socket.accept()
    _logger.info( 'Output socket connected' )


  def _Write( self, data ):
    assert self._client_write_socket

    total_sent = 0
    while total_sent < len( data ):
      sent = self._client_write_socket.send( data[ total_sent: ] )
      if sent == 0:
        raise RuntimeError( 'write socket failed' )

      total_sent += sent

    _logger.debug( 'Write complete' )


  def Read( self, size=-1 ):
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
    self._latest_diagnostics = {
      'uri': None,
      'diagnostics': []
    }
    self._syncType = 'Full'

    self._serverFileState = {}
    self._fileStateMutex = threading.Lock()
    self._server = LanguageServerConnection()


  def ComputeCandidatesInner( self, request_data ):
    # Need to update the file contents. TODO: so inefficient (and doesn't work
    # for the eclipse based completer for some reason)!
    self._RefreshFiles( request_data )

    request_id = self._server.NextRequestId()
    msg = lsapi.Completion( request_id, request_data )

    _logger.info( 'Sending completion request to server: {0}'.format( msg ) )
    response = self._server.GetResponse( request_id, msg )
    _logger.info( 'Got a response to completion: {0}'.format(
      json.dumps( response, indent=2 ) ) )

    def Falsy( key, item ):
      return key not in item or not item[ 'key' ]

    def MakeCompletion( item ):
      # First, resolve the completion.
      # TODO: Maybe we need some way to do this based on a trigger
      # TODO: Need a better API around request IDs. We no longer care about them
      # _at all_ here.
      # TODO: Only do this annoying step if the resolveProvider flag is true for
      # the server in question.
      resolve_id = self._server.NextRequestId()
      resolve = lsapi.ResolveCompletion( resolve_id, item )
      response = self._server.GetResponse( resolve_id, resolve )
      item = response[ 'result' ]

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
    self._RefreshFiles( request_data )

    def BuildLocation( filename, loc ):
      # TODO: Look at tern complete, requires file contents to convert codepoint
      # offset to byte offset
      return responses.Location( line = loc[ 'line' ] + 1,
                                 column = loc[ 'character' ] + 1,
                                 filename = os.path.realpath( filename ) )

    def BuildRange( filename, r ):
      return responses.Range( BuildLocation( filename, r[ 'start' ] ),
                              BuildLocation( filename, r[ 'end' ] ) )


    def BuildDiagnostic( filename, diag ):
      filename = lsapi.UriToFilePath( filename )
      r = BuildRange( filename, diag[ 'range' ] )
      SEVERITY = [
        None,
        'Error',
        'Warning',
        'Information',
        'Hint',
      ]
      SEVERITY_TO_YCM_SEVERITY = {
        'Error': 'ERROR',
        'Warning': 'WARNING',
        'Information': 'WARNING',
        'Hint': 'WARNING'
      }

      return responses.BuildDiagnosticData ( responses.Diagnostic(
        ranges = [ r ],
        location = r.start_,
        location_extent = r,
        text = diag[ 'message' ],
        kind = SEVERITY_TO_YCM_SEVERITY[ SEVERITY[ diag[ 'severity' ] ] ] ) )

    # TODO: Maybe we need to prevent duplicates? Anyway, handle all of the
    # notification messages
    latest_diagnostics = None
    try:
      while True:
        notification = self._server._diagnostics.get_nowait()
        _logger.debug( 'notification {0}: {1}'.format(
          notification[ 'method' ],
          json.dumps( notification[ 'params' ], indent = 2 ) ) )

        if notification[ 'method' ] == 'textDocument/publishDiagnostics':
          _logger.debug( 'latest_diagnostics updated' )
          latest_diagnostics = notification
    except queue.Empty:
      pass

    if latest_diagnostics is not None:
      _logger.debug( 'new diagnostics, updating latest received' )
      self._latest_diagnostics = latest_diagnostics[ 'params' ]
    else:
      _logger.debug( 'No new diagnostics, using latest received' )

    diags = [ BuildDiagnostic( self._latest_diagnostics[ 'uri' ], x )
              for x in self._latest_diagnostics[ 'diagnostics' ] ]
    _logger.debug( 'Diagnostics: {0}'.format( diags ) )
    return diags


  def PollForMessagesInner( self, request_data ):
    try:
      # TODO/FIXME: We should reduce the timeout if we loop
      while True:
        notification = self._server._notifications.get( timeout = 10 )
        _logger.info( 'Received notification: {0}'.format(
          json.dumps( notification, indent=2 ) ) )
        message = self._ConvertNotificationToMessage( request_data,
                                                      notification )
        if message:
          return message
    except queue.Empty:
      return True


  def _ConvertNotificationToMessage( self, request_data, notification ):
    if notification[ 'method' ] == 'window/showMessage':
      return responses.BuildDisplayMessageResponse(
        notification[ 'params' ][ 'message' ] )
    elif notification[ 'method' ] == 'language/status':
      return responses.BuildDisplayMessageResponse(
        'Language server status: {0}'.format(
          notification[ 'params' ][ 'message' ] ) )

    return None


  def _RefreshFiles( self, request_data ):
    with self._fileStateMutex:
      for file_name, file_data in request_data[ 'file_data' ].iteritems():
        file_state = 'New'
        if file_name in self._serverFileState:
          file_state = self._serverFileState[ file_name ]

        if file_state == 'New' or self._syncType == 'Full':
          msg = lsapi.DidOpenTextDocument( file_name,
                                           file_data[ 'filetypes' ],
                                           file_data[ 'contents' ] )
        else:
          # FIXME: DidChangeTextDocument doesn't actually do anything different
          # from DidOpenTextDocument because we don't actually have a mechanism
          # for generating the diffs (which would just be a waste of time)
          #
          # One option would be to just replcae the entire file, but some
          # servers (i'm looking at you javac completer) don't update
          # diagnostics until you open or save a document. Sigh.
          msg = lsapi.DidChangeTextDocument( file_name,
                                             file_data[ 'filetypes' ],
                                             file_data[ 'contents' ] )

        self._serverFileState[ file_name ] = 'Open'
        self._server.SendNotification( msg )

      for file_name in self._serverFileState.iterkeys():
        if file_name not in request_data[ 'file_data' ]:
          msg = lsapi.DidCloseTextDocument( file_name )
          del self._serverFileState[ file_name ]
          self._server.SendNotification( msg )


  def _WaitForInitiliase( self ):
    request_id = self._server.NextRequestId()

    msg = lsapi.Initialise( request_id )
    _logger.debug( 'Sending initialise request to server: {0}'.format( msg ) )
    response = self._server.GetResponse( request_id, msg )
    _logger.debug( 'Got a response to initialise: {0}'.format( response ) )

    if 'textDocumentSync' in response[ 'result' ][ 'capabilities' ]:
      SYNC_TYPE = [
        'None',
        'Full',
        'Incremental'
      ]
      self._syncType = SYNC_TYPE[
        response[ 'result' ][ 'capabilities' ][ 'textDocumentSync' ] ]
      _logger.info( 'Server requires sync type of {0}'.format(
        self._syncType ) )


  def _GetType( self, request_data ):
    request_id = self._server.NextRequestId()
    response = self._server.GetResponse( request_id,
                                         lsapi.Hover( request_id,
                                                      request_data ) )

    if isinstance( response[ 'result' ][ 'contents' ], list ):
      if len( response[ 'result' ][ 'contents' ] ):
        info = response[ 'result' ][ 'contents' ][ 0 ]
      else:
        raise RuntimeError( 'No information' )
    else:
      info = response[ 'result' ][ 'contents' ]

    return responses.BuildDisplayMessageResponse( str( info ) )
