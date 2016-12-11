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

import os
import json

from ycmd.utils import ToBytes


def BuildRequest( request_id, method, parameters ):
  return _Message( {
    'id': request_id,
    'method': method,
    'params': parameters,
  } )


def BuildNotification( method, parameters ):
  return {
    'method': method,
    'params': parameters,
  }


def Initialise( request_id ):
  return BuildRequest( request_id, 'initialize', {
    'processId': os.getpid(),
    # TODO: should this be the workspace path ? Hrm...
    'rootPath': os.getcwd(),
    'initializationOptions': { },
    'capabilities': { }
  } )


def _Message( message ):
  message[ 'jsonrpc' ] = '2.0'
  data = ToBytes( json.dumps( message ) )
  packet = ToBytes( 'Content-Length: {0}\r\n'
                    'Content-Type: application/vscode-jsonrpc;charset=utf8\r\n'
                    '\r\n'
                     .format( len(data) ) ) + data
  return packet


def Parse( data ):
  return json.loads( data )
