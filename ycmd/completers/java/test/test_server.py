#!/usr/bin/env python

from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
# Other imports from `future` must be placed after SetUpPythonPath.

import sys
import os

# TODO: Java 8 required (validate this)
PATH_TO_YCMD = os.path.join( os.path.dirname( __file__ ),
                             '..',
                             '..',
                             '..',
                             '..' )

sys.path.insert( 0, os.path.abspath( PATH_TO_YCMD ) )
from ycmd.server_utils import SetUpPythonPath
SetUpPythonPath()

from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import logging
import time

from ycmd import utils

PATH_TO_JAVA = utils.PathToFirstExistingExecutable( [ 'java' ] )
LANGUAGE_SERVER_HOME = os.path.join( os.path.dirname( __file__ ),
                                     '..',
                                     '..',
                                     '..',
                                     '..',
                                     'third_party',
                                     'java-language-server',
                                     'org.jboss.tools.vscode.product',
                                     'target',
                                     'repository')
WORKSPACE_PATH = os.path.join( os.path.dirname( __file__ ),
                               '..',
                               '..',
                               '..',
                               '..',
                               'third_party',
                               'java-language-server',
                               'jdt_ws' )


def SetUpLogging( log_level ):
  numeric_level = getattr( logging, log_level.upper(), None )
  if not isinstance( numeric_level, int ):
    raise ValueError( 'Invalid log level: %s' % log_level )

  # Has to be called before any call to logging.getLogger()
  logging.basicConfig( format = '%(asctime)s - %(levelname)s - %(message)s',
                       level = numeric_level )


from ycmd.completers.java.java_completer import Server
import subprocess
from ycmd.completers.java.java_completer import lsapi


def _ReadMessage( server ):
  headers = {}
  logger = logging.getLogger( __file__ )

  headers_complete = False
  while not headers_complete:
    read_bytes = 0
    last_line = 0
    data = server.Read()

    logger.debug( 'read data: {0}'.format( data ) )

    while read_bytes < len( data ):
      if data[ read_bytes ] == bytes( b'\n' ):
        line = data[ last_line : read_bytes ].strip()
        last_line = read_bytes
        logger.debug( 'read line: {0}'.format( line ) )
        if not line:
          logger.debug( 'empty line, headers complete' )
          headers_complete = True
          read_bytes += 1
          break
        else:
          key, value = utils.ToUnicode( line ).split( ':', 1 )
          logger.debug( 'read header {0} = {1}'.format( key.strip(),
                                                       value.strip() ) )
          headers[ key.strip() ] = value.strip()

      read_bytes += 1

  # The response message is a JSON object which comes back on one line.
  # Since this might change in the future, we use the 'Content-Length'
  # header.
  if 'Content-Length' not in headers:
    raise RuntimeError( "Missing 'Content-Length' header" )
  content_length = int( headers[ 'Content-Length' ] )

  logger.debug( 'Need to read {0} bytes'.format( content_length ) )

  content = bytes( b'' )
  content_read = 0
  if read_bytes < len( data ):
    data = data[ read_bytes: ]
    content_to_read = min( content_length - content_read, len( data ) )
    content += data[ : content_to_read ]
    content_read += len( content )

  logger.debug( 'Read {0} from header packet'.format( content ) )

  while content_read < content_length:
    logger.debug( 'Blocking to read {0} bytes of body'.format(
      content_length - content_read ) )
    data = server.Read( content_length - content_read )
    content_to_read = min( content_length - content_read, len( data ) )
    content += data[ : content_to_read ]
    content_read += len( content )

  logger.debug( 'Read message: {0}'.format( content ) )
  return lsapi.Parse( content )


if __name__ == '__main__':
  SetUpLogging( 'debug' )

  if 1:
    from ycmd.completers.java.hook import GetCompleter
    from ycmd.user_options_store import DefaultOptions
    completer = GetCompleter( DefaultOptions() )
  else:
    STDIN_PORT = utils.GetUnusedLocalhostPort()
    STDOUT_PORT = utils.GetUnusedLocalhostPort()

    server = Server( STDIN_PORT, STDOUT_PORT )

    server.start()

    env = os.environ.copy()
    env[ 'STDIN_PORT' ] = str( STDIN_PORT )
    env[ 'STDOUT_PORT' ] = str( STDOUT_PORT  )

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

    logger = logging.getLogger( __name__ )
    logger.debug(
      'Starting tern with the following command: ' + ' '.join( command ) )

    server_stdout = 'server_stdout'
    server_stderr = 'server_stderr'

    logger.debug( 'server_stdout: {0}'.format( server_stdout ) )
    logger.debug( 'server_stderr: {0}'.format( server_stderr ) )

    with utils.OpenForStdHandle( server_stdout ) as stdout:
      with utils.OpenForStdHandle( server_stderr ) as stderr:
        server_handle = utils.SafePopen( command,
                                         stdin = subprocess.PIPE,
                                         stdout = stdout,
                                         stderr = stderr,
                                         env = env )

    # spinlock
    while not server.TryServerConnection():
      logger.debug( 'Awaiting connection on ports: IN {0}, OUT {1}'.format(
        STDIN_PORT, STDOUT_PORT ) )
      time.sleep( 1 )

    req = lsapi.Initialise( 0 )
    logger.info( 'Sending initialise request to server: {0}'.format( req ) )
    server.Write( req )

    rep = _ReadMessage( server )
    logger.info( 'Get message {0}'.format( rep ) )
