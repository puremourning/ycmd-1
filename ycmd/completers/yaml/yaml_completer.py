# Copyright (C) 2018 ycmd contributors
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

from ycmd.completers.language_server import (
  simple_language_server_completer as slsc )
from ycmd import utils
from ycmd.utils import LOGGER

import os

PATH_TO_SERVER = os.path.abspath(
  os.path.join(
    os.path.dirname( __file__ ),
    '..',
    '..',
    '..',
    'third_party',
    'yaml-Language-server-runtime',
    'node_modules',
    '.bin',
    'yaml-language-server' ) )

PATH_TO_NODE = utils.FindExecutable( 'node' )


def ShouldEnableYAMLCompleter():
  if not os.path.exists( PATH_TO_SERVER ):
    LOGGER.info( "Not using YAML completer: not installed" )
    return False

  if not PATH_TO_NODE:
    LOGGER.warning( "Not using YAML completer: can't find node" )
    return False

  LOGGER.info( "YAML completer is ready to use" )
  return True


class YAMLCompleter( slsc.SimpleLSPCompleter ):
  def __init__( self, user_options ):
    super( YAMLCompleter, self ).__init__( user_options )


  def GetServerName( self ):
    return 'yaml-language-server'


  def GetCommandLine( self ):
    return [ PATH_TO_NODE, PATH_TO_SERVER, '--stdio' ]


  def SupportedFiletypes( self ):
    return [ 'yaml' ]
