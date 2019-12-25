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

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
# Not installing aliases from python-future; it's unreliable and slow.
from builtins import *  # noqa

from ycmd import responses
from ycmd.utils import LOGGER, FindExecutable
from ycmd.completers.language_server import simple_language_server_completer

SOURCEKIT_LSP_EXECUTABLE = FindExecutable( 'sourcekit-lsp' )


def ShouldEnableSwiftCompleter():
  if not FindExecutable( 'swift' ):
    LOGGER.error( 'Not using Swift completer: no swift compiler found.' )
    return False
  if not SOURCEKIT_LSP_EXECUTABLE:
    LOGGER.error( 'Not using Swift completer: '
                  'no sourcekit-lsp executable found found.' )
    return False
  LOGGER.info( 'Using Swift completer' )
  return True


class SwiftCompleter( simple_language_server_completer.SimpleLSPCompleter ):
  def GetServerName( self ):
    return 'Swift Language Server'


  def GetCommandLine( self ):
    return SOURCEKIT_LSP_EXECUTABLE


  def GetProjectRootFiles( self ):
    return [ 'Package.swift' ]

  def SupportedFiletypes( self ):
    return [ 'swift' ]


  def GetCustomSubcommands( self ):
    return {
      'FixIt': (
        lambda self, request_data, args:
          self.GetCodeActions( request_data, args ) )
    }


  def _GoToRequest( self, request_data, handler ):
    goto_response = super( simple_language_server_completer.SimpleLSPCompleter,
                           self )._GoToRequest( request_data, handler )
    goto_response = list( filter(
        lambda l: not l[ 'uri' ].endswith( '.swiftmodule' ), goto_response ) )
    if not goto_response:
      raise RuntimeError( 'Cannot jump to location' )
    return goto_response


  def GetDoc( self, request_data ):
    hover_response = self.GetHoverResponse( request_data )
    return responses.BuildDetailedInfoResponse( hover_response[ 'value' ] )


  def GetType( self, request_data ):
    hover_response = self.GetHoverResponse( request_data )[ 'value' ]
    first_new_line = hover_response.find( '\n' ) + 1
    start = hover_response.find( '\n', first_new_line ) + 1
    end = hover_response.find( '\n', start + 1 )
    return responses.BuildDetailedInfoResponse( hover_response[ start : end ] )


  def ComputeCandidatesInner( self, request_data, codepoint ):
    raw_completions, is_incomplete = super(
        simple_language_server_completer.SimpleLSPCompleter,
        self ).ComputeCandidatesInner( request_data, codepoint )
    for item in raw_completions:
      insertion_text = item[ 'insertion_text' ]
      insertion_text_end = insertion_text.rfind( '(' )
      if insertion_text_end != -1:
        item[ 'insertion_text' ] = insertion_text[ : insertion_text_end ]
    return raw_completions, is_incomplete
