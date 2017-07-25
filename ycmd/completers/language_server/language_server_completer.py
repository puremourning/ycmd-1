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
import re

from ycmd.completers.completer import Completer
# from ycmd.completers.completer_utils import GetFileContents
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
    self._event.wait( timeout = 1 )

    if not self._event.isSet():
      raise RuntimeError( 'Response Timeout' )

    if 'error' in self._message:
      error = self._message[ 'error' ]
      raise RuntimeError( 'Request failed: {0}: {1}'.format(
        error.get( 'code', 0 ),
        error.get( 'message', 'No message' ) ) )

    return self._message


class LanguageServerConnection( object ):
  """
    Abstract language server communication object.

    Implementations are required to provide the following methods:
      - _TryServerConnectionBlocking: Connect to the server and return when the
                                      connection is established
      - _Write: Write some data to the server
      - _Read: Read some data from the server, blocking until some data is
               available
  """
  def __init__( self ):
    super( LanguageServerConnection, self ).__init__()

    self._lastId = 0
    self._responses = {}
    self._responseMutex = threading.Lock()
    self._notifications = queue.Queue()

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

    _logger.debug( 'TX: Sending message {0}'.format(
      json.dumps( message, indent=2 ) ) )

    self._Write( message )
    return response.AwaitResponse()


  def SendNotification( self, message ):
    _logger.debug( 'TX: Sending Notification {0}'.format(
      json.dumps( message, indent=2 ) ) )
    self._Write( message )


  def TryServerConnection( self ):
    self._connection_event.wait( timeout = 10 )

    if not self._connection_event.isSet():
      raise RuntimeError( 'Timed out waiting for server to connect' )


  def _run_loop( self ):
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
        data = self._Read()

      while read_bytes < len( data ):
        if data[ read_bytes ] == bytes( b'\n' ):
          line = prefix + data[ last_line : read_bytes ].strip()
          prefix = ''
          last_line = read_bytes

          if not line.strip():
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
        data = self._Read( content_length - content_read )
        content_to_read = min( content_length - content_read, len( data ) )
        content += data[ : content_to_read ]
        content_read += len( content )
        read_bytes = content_to_read

      self._DespatchMessage( lsapi.Parse( content ) )

      # We only consumed len( content ) of data. If there is more, we start
      # again with the remainder and look for headers
      data = data[ read_bytes : ]


  def _DespatchMessage( self, message ):
    _logger.debug( 'RX: Received message: {0}'.format( message ) )
    if 'id' in message:
      with self._responseMutex:
        assert str( message[ 'id' ] ) in self._responses
        self._responses[ str( message[ 'id' ] ) ].ResponseReceived( message )
    else:
      self._notifications.put( message )


  def _TryServerConnectionBlocking( self ):
    raise RuntimeError( 'Not implemented' )


  def _Write( self, data ):
    raise RuntimeError( 'Not implemented' )


  def _Read( self, size=-1 ):
    raise RuntimeError( 'Not implemented' )



class TCPSingleStreamServer( LanguageServerConnection, threading.Thread ):
  def __init__( self, port ):
    super( TCPSingleStreamServer, self ).__init__()

    self._port = port
    self._socket = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
    self._client_socket = None


  def run( self ):
    self._socket.bind( ( 'localhost', self._port ) )
    self._socket.listen( 0 )

    self._run_loop()


  def _TryServerConnectionBlocking( self ):
    ( self._client_socket, _ ) = self._socket.accept()
    _logger.info( 'language server socket connected' )

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


  def _Read( self, size=-1 ):
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

    self._run_loop()


  def _TryServerConnectionBlocking( self ):
    ( self._client_read_socket, _ ) = self._input_socket.accept()
    _logger.info( 'Language server Input socket connected' )

    ( self._client_write_socket, _ ) = self._output_socket.accept()
    _logger.info( 'Language server Output socket connected' )


  def _Write( self, data ):
    assert self._client_write_socket

    total_sent = 0
    while total_sent < len( data ):
      sent = self._client_write_socket.send( data[ total_sent: ] )
      if sent == 0:
        raise RuntimeError( 'write socket failed' )

      total_sent += sent


  def _Read( self, size=-1 ):
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


class StandardIOLanguageServerConnection( LanguageServerConnection,
                                          threading.Thread ):
  def __init__( self, server_stdin, server_stdout ):
    super( StandardIOLanguageServerConnection, self ).__init__()

    self.server_stdin = server_stdin
    self.server_stdout = server_stdout


  def run( self ):
    self._run_loop()


  def _TryServerConnectionBlocking( self ):
    return True


  def _Write( self, data ):
    to_write = data + utils.ToBytes( '\r\n' )
    self.server_stdin.write( to_write )
    self.server_stdin.flush()


  def _Read( self, size=-1 ):
    if size > -1:
      data = self.server_stdout.read( size )
    else:
      data = self.server_stdout.readline()

    if not data:
      # The connection diea
      raise RuntimeError( "Connection to server died" )

    return data


class LanguageServerCompleter( Completer ):
  def __init__( self, user_options):
    super( LanguageServerCompleter, self ).__init__( user_options )

    self._syncType = 'Full'

    self._serverFileState = {}
    self._fileStateMutex = threading.Lock()


  def GetServer( sefl ):
    """Method that must be implemented by derived classes to return an instance
    of LanguageServerConnection appropriate for the language server in
    question"""
    # TODO: I feel like abc.abstractmethod could be used here, but I'm not sure
    # if it is totally python2/3 safe, and TBH it doesn't do a lot more than
    # this simple raise here, so...
    raise NameError( "GetServer must be implemented in LanguageServerCompleter "
                     "subclasses" )


  def ComputeCandidatesInner( self, request_data ):
    # Need to update the file contents. TODO: so inefficient (and doesn't work
    # for the eclipse based completer for some reason - possibly because it
    # is busy parsing the file when it actually should be providing
    # completions)!
    self._RefreshFiles( request_data )

    request_id = self.GetServer().NextRequestId()
    msg = lsapi.Completion( request_id, request_data )
    response = self.GetServer().GetResponse( request_id, msg )

    do_resolve = (
      'completionProvider' in self._server_capabilities and
      self._server_capabilities[ 'completionProvider' ].get( 'resolveProvider',
                                                             False ) )

    def MakeCompletion( item ):
      # First, resolve the completion.
      # TODO: Maybe we need some way to do this based on a trigger
      # TODO: Need a better API around request IDs. We no longer care about them
      # _at all_ here.

      if do_resolve:
        resolve_id = self.GetServer().NextRequestId()
        resolve = lsapi.ResolveCompletion( resolve_id, item )
        response = self.GetServer().GetResponse( resolve_id, resolve )
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

      ( insertion_text, fixits ) = self._GetInsertionText( request_data, item )
      return responses.BuildCompletionData(
        insertion_text,
        None,
        None,
        item[ 'label' ],
        ITEM_KIND[ item.get( 'kind', 0 ) ],
        fixits )

    if isinstance( response[ 'result' ], list ):
      items = response[ 'result' ]
    else:
      items = response[ 'result' ][ 'items' ]
    return [ MakeCompletion( i ) for i in items ]


  def OnFileReadyToParse( self, request_data ):
    self._RefreshFiles( request_data )

    # NOTE: We return diagnostics asynchronously via the long-polling mechanism
    # because there's a big-old timing issue in that the above refresh doesn't
    # return diagnostics immediately; we end up lagging at least one parse
    # request behind. On slow completers (I'm looking at you eclipse), this
    # leads to a poor user experience.


  def PollForMessagesInner( self, request_data ):
    try:
      while True:
        notification = self.GetServer()._notifications.get( timeout = 10 )
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
    elif notification[ 'method' ] == 'language/actionableNotification':
      # TODO: YcmCompleter subcommand to action these!
      # TODO: Severity / warning etc. in the response
      return responses.BuildDisplayMessageResponse(
        'Language server reported: {0}'.format(
          notification[ 'params' ][ 'message' ] ) )
    elif notification[ 'method' ] == 'textDocument/publishDiagnostics':
      latest_diagnostics = notification[ 'params' ]
      response = {
        'diagnostics': [ BuildDiagnostic( latest_diagnostics[ 'uri' ], x )
                         for x in latest_diagnostics[ 'diagnostics' ] ]
      }
      return response

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
          # One option would be to just replace the entire file, but some
          # servers (I'm looking at you javac completer) don't update
          # diagnostics until you open or save a document. Sigh.
          msg = lsapi.DidChangeTextDocument( file_name,
                                             file_data[ 'filetypes' ],
                                             file_data[ 'contents' ] )

        self._serverFileState[ file_name ] = 'Open'
        self.GetServer().SendNotification( msg )

      for file_name in self._serverFileState.iterkeys():
        if file_name not in request_data[ 'file_data' ]:
          msg = lsapi.DidCloseTextDocument( file_name )
          del self._serverFileState[ file_name ]
          self.GetServer().SendNotification( msg )


  def _WaitForInitiliase( self ):
    request_id = self.GetServer().NextRequestId()

    msg = lsapi.Initialise( request_id )
    response = self.GetServer().GetResponse( request_id, msg )

    self._server_capabilities = response[ 'result' ][ 'capabilities' ]

    if 'textDocumentSync' in response[ 'result' ][ 'capabilities' ]:
      SYNC_TYPE = [
        'None',
        'Full',
        'Incremental'
      ]
      self._syncType = SYNC_TYPE[
        response[ 'result' ][ 'capabilities' ][ 'textDocumentSync' ] ]
      _logger.info( 'Language Server requires sync type of {0}'.format(
        self._syncType ) )


  def _GetType( self, request_data ):
    request_id = self.GetServer().NextRequestId()
    response = self.GetServer().GetResponse( request_id,
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


  def _GoToDeclaration( self, request_data ):
    request_id = self.GetServer().NextRequestId()
    response = self.GetServer().GetResponse( request_id,
                                             lsapi.Definition( request_id,
                                                               request_data ) )

    if isinstance( response[ 'result' ], list ):
      if len( response[ 'result' ] ) > 1:
        positions = response[ 'result' ]
        return [
          responses.BuildGoToResponseFromLocation(
            # TODO: Codepoint to byte offset
            responses.Location(
              position[ 'range' ][ 'start' ][ 'line' ] + 1,
              position[ 'range' ][ 'start' ][ 'character' ] + 1,
              lsapi.UriToFilePath( position[ 'uri' ] ) )
          ) for position in positions
        ]
      else:
        position = response[ 'result' ][ 0 ]
        return responses.BuildGoToResponseFromLocation(
          # TODO: Codepoint to byte offset
          responses.Location( position[ 'range' ][ 'start' ][ 'line' ] + 1,
                              position[ 'range' ][ 'start' ][ 'character' ] + 1,
                              lsapi.UriToFilePath( position[ 'uri' ] ) )
        )
    else:
      position = response[ 'result' ]
      return responses.BuildGoToResponseFromLocation(
        # TODO: Codepoint to byte offset
        responses.Location( position[ 'range' ][ 'start' ][ 'line' ] + 1,
                            position[ 'range' ][ 'start' ][ 'character' ] + 1,
                            lsapi.UriToFilePath( position[ 'uri' ] ) )
      )

  def _GetInsertionText( self, request_data, item ):
    # TODO: We probably need to implement this and (at least) strip out the
    # snippet parts?
    INSERT_TEXT_FORMAT = [
      None, # 1-based
      'PlainText',
      'Snippet'
    ]

    fixits = None

    # Per the protocol, textEdit takes precedence over insertText, and must be
    # on the same line (and containing) the originally requested position
    if 'textEdit' in item and item[ 'textEdit' ]:
      new_range = item[ 'textEdit' ][ 'range' ]
      if ( new_range[ 'start' ][ 'line' ] != new_range[ 'end' ][ 'line' ] or
           new_range[ 'start' ][ 'line' ] + 1 != request_data[ 'line_num' ] ):
        # We can't support completions that span lines. The protocol forbids it
        raise RuntimeError( 'Invalid textEdit supplied. Must be on a single '
                            'line' )
      else:
        request_data[ 'start_codepoint' ] = (
          new_range[ 'start' ][ 'character' ] + 1 )
        insertion_text = item[ 'textEdit' ][ 'newText' ]

      additionalTextEdits = item.get( 'additionalTextEdits', None )

      if additionalTextEdits:
        chunks = [ responses.FixItChunk( e[ 'newText' ],
                                         BuildRange( request_data[ 'filepath' ],
                                                     e[ 'range' ] ) )
                   for e in additionalTextEdits ]

        fixits = responses.BuildFixItResponse(
          [ responses.FixIt( chunks[ 0].range.start_, chunks ) ] )

    elif 'insertText' in item and item[ 'insertText' ]:
      insertion_text = item[ 'insertText' ]
    else:
      insertion_text = item[ 'label' ]

    if 'insertTextFormat' in item and item[ 'insertTextFormat' ]:
      text_format = INSERT_TEXT_FORMAT[ item[ 'insertTextFormat' ] ]
    else:
      text_format = 'PlainText'

    if text_format == 'Snippet':
      # TODO: This is not the snippet format! This is the format that was
      # secretly supported in vscode, but has been superseded by a real format
      # which is more like SnipMate
      #
      # FIXME!
      insertion_text = re.sub( '{{[^}]*}}', '', insertion_text )

    return ( insertion_text, fixits )


def BuildLocation( filename, loc ):
  # TODO: Look at tern completer, requires file contents to convert
  # codepoint offset to byte offset
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

