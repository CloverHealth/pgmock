"""
pgmock
------

Primary ``pgmock`` interface
"""
from pgmock.version import __version__  # flake8: noqa

import pgmock.config
from pgmock.mocker import data
from pgmock.mocker import mock
from pgmock.mocker import patch
from pgmock.render import sql
from pgmock.render import sql_file
from pgmock.selector import body
from pgmock.selector import create_table_as
from pgmock.selector import cte
from pgmock.selector import statement
from pgmock.selector import insert_into
from pgmock.selector import subquery
from pgmock.selector import table


__all__ = [
    'config',
    'create_table_as',
    'cte',
    'data',
    'mock',
    'patch',
    'sql',
    'sql_file',
    'statement',
    'insert_into',
    'subquery',
    'table'
]
