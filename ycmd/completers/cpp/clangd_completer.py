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

from ycmd.completers.language_server.language_server_completer import (
  StandardIOLanguageServerConnection,
  LanguageServerCompleter,
  LanguageServerConnectionTimeout )
from ycmd import utils, responses
from ycmd.completers.cpp.flags import Flags, NoCompilationDatabase
from ycmd.completers.cpp.clang_completer import FlagsForRequest

import threading
import logging
import os
from subprocess import PIPE


_logger = logging.getLogger( __name__ )


def ShouldEnableClangdCompleter( user_options ):
  return bool( user_options.get( 'path_to_clangd', '' ) )


class ClangdCopleter( LanguageServerCompleter ):
  def __init__( self, user_options ):
    super( ClangdCopleter, self ).__init__( user_options )

    self._flags = Flags()
    self._server_keep_logfiles = user_options[ 'server_keep_logfiles' ]
    self._path_to_clangd = user_options[ 'path_to_clangd' ]
    self._connection = None
    self._server_handle = None
    self._server_stderr = None
    self._server_state_mutex = threading.RLock()
    self._server_started = False
    self._CleanUp()


  def SupportedFiletypes( self ):
    return [ 'cpp' ] # TODO, C, objective-c


  def GetSubcommandsMap( self ):
    return {
      # Handled by base class
      'GoToDeclaration': (
        lambda self, request_data, args: self.GoToDeclaration( request_data )
      ),
      'GoTo': (
        lambda self, request_data, args: self.GoToDeclaration( request_data )
      ),
      'GoToDefinition': (
        lambda self, request_data, args: self.GoToDeclaration( request_data )
      ),
      'GoToReferences': (
        lambda self, request_data, args: self.GoToReferences( request_data )
      ),
      'FixIt': (
        lambda self, request_data, args: self.GetCodeActions( request_data,
                                                              args )
      ),
      'RefactorRename': (
        lambda self, request_data, args: self.RefactorRename( request_data,
                                                              args )
      ),
      'Format': (
        lambda self, request_data, args: self.Format( request_data )
      ),

      # Handled by us
      'RestartServer': (
        lambda self, request_data, args: self._RestartServer( request_data )
      ),
      'StopServer': (
        lambda self, request_data, args: self._StopServer()
      ),
    }


  def GetConnection( self ):
    return self._connection


  def OnFileReadyToParse( self, request_data ):
    self._StartServer( request_data )

    return super( ClangdCopleter, self ).OnFileReadyToParse( request_data )


  def DebugInfo( self, request_data ):
    items = [
      responses.DebugInfoItem( 'DB Directory',
                               self._database_directory or 'None' ),
    ]
    return responses.BuildDebugInfoResponse(
      name = "clangd",
      servers = [
        responses.DebugInfoServer(
          name = "clangd",
          handle = self._server_handle,
          executable = self._path_to_clangd,
          logfiles = [
            self._server_stderr,
          ],
          extras = items
        )
      ] )


  def Shutdown( self ):
    self._StopServer()


  def ServerIsHealthy( self ):
    return utils.ProcessIsRunning( self._server_handle )


  def HandleServerCommand( self, request_data, command ):
    return None


  def _StartServer( self, request_data ):
    with self._server_state_mutex:
      if self._server_started:
        return False

      self._server_started = True

      try:
        self._database_directory = self._flags.FindCompilationDatabase(
            os.path.dirname( request_data[ 'filepath' ] ) ).database_directory
      except NoCompilationDatabase:
        pass

      _logger.info( 'Starting clangd...' )

      command = [
        self._path_to_clangd,
        '-input-style=standard',
        '-j=8',
        '-pch-storage=memory'
      ]

      if self._database_directory:
        command.append( '-compile-commands-dir=' + self._database_directory )

      _logger.debug( 'Starting clangd with the following command: '
                     '{0}'.format( ' '.join( command ) ) )

      self._server_stderr = utils.CreateLogfile( 'clangd_stderr_' )
      with utils.OpenForStdHandle( self._server_stderr ) as stderr:
        self._server_handle = utils.SafePopen( command,
                                               stdin = PIPE,
                                               stdout = PIPE,
                                               stderr = stderr )

      self._connection = StandardIOLanguageServerConnection(
        self._server_handle.stdin,
        self._server_handle.stdout,
        self.GetDefaultNotificationHandler() )
      self._connection.Start()

      try:
        self._connection.AwaitServerConnection()
      except LanguageServerConnectionTimeout:
        _logger.error( 'clangd failed to start, or did not connect '
                       'successfully' )
        self._StopServer()
        return

    _logger.info( 'jdt.ls Language Server started' )

    self.SendInitialize( request_data )


  def _StopServer( self ):
    with self._server_state_mutex:
      _logger.info( 'Shutting down clangd...' )

      # Tell the connection to expect the server to disconnect
      if self._connection:
        self._connection.Stop()

      if not self.ServerIsHealthy():
        _logger.info( 'clangd not running' )
        self._CleanUp()
        return

      _logger.info( 'Stopping clangd with PID {0}'.format(
                        self._server_handle.pid ) )

      try:
        self.ShutdownServer()

        # By this point, the server should have shut down and terminated. To
        # ensure that isn't blocked, we close all of our connections and wait
        # for the process to exit.
        #
        # If, after a small delay, the server has not shut down we do NOT kill
        # it; we expect that it will shut itself down eventually. This is
        # predominantly due to strange process behaviour on Windows.
        if self._connection:
          self._connection.Close()

        utils.WaitUntilProcessIsTerminated( self._server_handle,
                                            timeout = 15 )

        _logger.info( 'clangd stopped' )
      except Exception:
        _logger.exception( 'Error while stopping clangd' )
        # We leave the process running. Hopefully it will eventually die of its
        # own accord.

      # Tidy up our internal state, even if the completer server didn't close
      # down cleanly.
      self._CleanUp()
      pass


  def _CleanUp( self ):
    if not self._server_keep_logfiles:
      if self._server_stderr:
        utils.RemoveIfExists( self._server_stderr )
        self._server_stderr = None

    self._server_started = False
    self._server_handle = None
    self._connection = None
    self._database_directory = None
    self.ServerReset()


  def _RestartServer( self, request_data ):
    with self._server_state_mutex:
      self._StopServer()
      self._StartServer()


  def Customize( self, message, request_data ):
    if message[ 'method' ] == 'textDocument/didOpen':
      py_flags = [
        flag for flag in FlagsForRequest( self._flags, request_data )
      ]
      message[ 'params' ][ 'metadata' ] = {
        'extraFlags': py_flags
      }

    return message
