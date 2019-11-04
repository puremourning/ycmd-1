# Copyright (C) 2011-2019 ycmd contributors
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


class IgnoreExtraConf( Exception ):
  """Raise this exception from within a FlagsForFile or Settings function to
  instruct ycmd to ignore this module for the current file.

  For example, if you wish to delegate to ycmd's built-in compilation database
  support, you can write:

    from ycmd.extra_conf_support import IgnoreExtraConf

    def Settings( **kwargs ):
      if kwargs[ 'language' ] == 'c-family':
        # Use compilation database
        raise IgnoreExtraConf()

      if kwargs[ 'language' ] == 'python':
        ...

  This will then tell ycmd to use your compile_commands.json, or global extra
  conf as if this local module doens't exist.
  """
  pass
