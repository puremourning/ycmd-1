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
from builtins import *  # noqa
from future import standard_library
standard_library.install_aliases()

import logging
import os
import subprocess

from ycmd.completers.language_server import language_server_completer
from ycmd import responses, utils

PATH_TO_CLANGD = utils.PathToFirstExistingExecutable( [ 'clangd' ] )


_logger = logging.getLogger( __name__ )


def ShouldEnableClangdCompleter():
  return bool( PATH_TO_CLANGD )


class ClangdCompleter( language_server_completer.LanguageServerCompleter ):
  def __init__( self, user_options ):
    super( ClangdCompleter, self ).__init__( user_options )

    self._server = None
    self._server_handle = None
    self._server_stderr = None

    try:
      self._StartServer()
    except:
      _logger.exception( "The clangd server failed to start." )
      self._StopServer()


  def GetServer( self ):
    return self._server


  def ShouldUseNowInner( self, request_data ):
    if not self.ServerIsReady():
      return False

    return super( ClangdCompleter, self ).ShouldUseNowInner( request_data )


  def SupportedFiletypes( self ):
    return [ 'cpp' ]


  def DebugInfo( self, request_data ):
    return responses.BuildDebugInfoResponse(
      name = "Clangd",
      servers = [
        responses.DebugInfoServer(
          name = "Clangd Language Server",
          handle = self._server_handle,
          executable = PATH_TO_CLANGD,
          logfiles = [ self._server_stderr ]
        )
      ] )


  def Shutdown( self ):
    self._StopServer()


  def ServerIsHealthy( self, request_data = {} ):
    return self._ServerIsRunning()


  def GetSubcommandsMap( self ):
    return {
      'RestartServer': ( lambda self, request_data, args:
                            self._RestartServer() ),
    }


  def HandleServerCommand( self, request_data, command ):
    return None


  def _RestartServer( self ):
    self._StopServer()
    self._StartServer()


  def _StartServer( self ):
    self._server_stderr = utils.CreateLogfile(
      'clangd_stderr_{0}'.format( os.getpid() ) )

    with utils.OpenForStdHandle( self._server_stderr ) as stderr:
      self._server_handle = utils.SafePopen(
        [ PATH_TO_CLANGD ],
        stdin = subprocess.PIPE,
        stdout = subprocess.PIPE,
        stderr = stderr )

    if not self._ServerIsRunning():
      raise RuntimeError( "Unable to start clangd" )

    self._server = language_server_completer.StandardIOLanguageServerConnection(
      self._server_handle.stdin,
      self._server_handle.stdout )

    self._server.start()

    try:
      self._server.TryServerConnection()
    except language_server_completer.LanguageServerConnectionTimeout:
      _logger.warn( 'Java language server failed to start, or did not '
                    'connect successfully' )
      self._StopServer()
      return

    self._WaitForInitiliase()


  def _StopServer( self ):
    if self._ServerIsRunning():
      self._server_handle.terminate()
      try:
        utils.WaitUntilProcessIsTerminated( self._server_handle,
                                            timeout = 5 )
        _logger.info( 'Clangd server stopped' )
      except RuntimeError:
        _logger.exception( 'Error while stopping clangd server' )

    self._server = None
    self._server_handle = None
    self._server_stderr = None


  def _ServerIsRunning( self ):
    return utils.ProcessIsRunning( self._server_handle )
