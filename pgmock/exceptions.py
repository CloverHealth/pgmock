"""
These are all of the custom exceptions thrown by ``pgmock``. The descriptions of most of the
exceptions talk about common scenarios that can cause the exceptions to be raised.
"""

DOCS_URL = (
    'https://pgmock.readthedocs.io/en/latest/exceptions.html'
)


class Error(Exception):
    """The base exception for ``pgmock``"""


class SQLParseError(Error):
    """Top-level error thrown when parsing SQL expressions"""


class InvalidSQLError(SQLParseError):
    """Thrown when invalid SQL is loaded with pgmock.

    This error is thrown when no matches are found for enclosing parentheses.
    For example, matching a CTE with the following SQL::

        WITH cte_name AS (SELECT * from table

    would produce this error since there is no matching right paren for the
    initial left paren.
    """


class StatementParseError(SQLParseError):
    """Thrown when statements cannot be parsed.

    This happens when trying to obtain a statement in a SQL
    query and the index is out of the bounds of the number of
    statements.

    Keep in mind that when using `pgmock.statement` that the
    first argument is the index of the first statement starting
    at 0.
    """


class NoMatchError(SQLParseError):
    """Thrown when parsing an expression and not finding a match.

    This error commonly happens when using a selector that takes
    a name (such as ``pgmock.subquery('subquery_name')``) and not
    being able to find a match for the given name.

    Please read the docs for the selector that you are using and
    check that you have provided all of the proper arguments first.
    For example, selecting a table that has an alias requires also
    passing its alias or this error will be raised.

    If you are certain that your selector is referencing a valid
    name in your query, contact the authors or open up an
    issue at https://github.com/CloverHealth/pgmock with the
    entire exception message provided and code.
    """


class MultipleMatchError(SQLParseError):
    """Thrown when multiple matches are rendered.

    This error happens when a selector finds multiple occurrences
    of a SQL expression and it is either rendered or has other
    selectors chained to it.

    For example, say your SQL is::

        CREATE TABLE a AS ( SELECT * FROM t1 ) ;
        CREATE TABLE a AS ( SELECT * FROM t2 ) ;

    Doing::

        pgmock.sql(sql, pgmock.create_table_as('a'))

    Will result in a `MultipleMatchError` since multiple ``CREATE TABLE AS``
    expressions were found and ``pgmock`` tried to obtain the SQL for it.
    One must refine the selection with list syntax to choose which
    one is rendered like so::

        pgmock.sql(sql, pgmock.create_table_as('a')[0])

    The above will return the SQL for the first ``CREATE TABLE AS``
    expression.

    The same situation holds true when chaining selectors. A selector
    cannot be chained to one that results in multiple matches.
    For example, the following selector is invalid for use in
    any pgmock function (including `pgmock.patch`)::

        pgmock.create_table_as('a').body()

    .. note::

        It is possible to select multiple occurences of some expressions
        when patching them (such as tables). This only holds true for
        selectors given to `pgmock.patch` like so::

            pgmock.sql(sql, pgmock.patch(pgmock.create_table_as('a'), values))
    """


class NestedMatchError(MultipleMatchError):
    """Thrown when a selector selects a nested pattern

    For example, imagine we have the following SQL::

        SELECT * FROM (
            SELECT * FROM (
                SELECT * FROM test_table
            ) bb
        ) bb

    The following code will produce this error::

        pgmock.sql(sql, pgmock.subquery('bb'))

    This is because subqueries (along with CTEs) can have nested patterns,
    and it is ambiguous how pgmock should patch or select them
    """


class SelectorChainingError(Error):
    """Thrown when trying to chain together selectors that can't be chained.

    ``pgmock`` allows selectors to be chained into one single selector like so::

        selector = pgmock.patch(...).patch(...)
        sql = pgmock.sql(my_sql_string, selector)

    Sometimes it isn't always feasible to chain together multiple selectors, so
    pgmock allows multiple selectors to be passed to ``pgmock.sql`` like so::

        sql = pgmock.sql(my_sql_string, pgmock.patch(...), pgmock.patch(...))

    The syntax from the latter is equivalent to the syntax from the former.

    This exception is raised when using the syntax from the latter example and
    using selectors that are impossible to be chained together. For example,
    pgmock doesn't allow this selector to be constructed::

        pgmock.patch(...).subquery(...)

    The above isn't allowed because patches effectively stop any other selectors
    from further refining the view of SQL being rendered.

    This error is raised when an invalid chain such as the one from above is passed
    to ``pgmock.sql`` or ``pgmock.sql_file`` using multiple selectors.
    """


class PatchError(Error):
    """Top-level patching error"""


class UnpatchableError(PatchError):
    """Thrown when an expression cannot be patched.

    This error is thrown when trying to patch SQL that is not patchable or currently
    not supported by ``pgmock``. Since patching is only applicable to expressions that can
    be translated into Postgres ``VALUES`` statements, sometimes it is not possible to
    patch an expression.

    For example, trying to patch the first two statements of a query with
    ``pgmock.patch(pgmock.statement(0, 2), ...)`` would throw this error since it is
    not possible to patch two entire statements.
    """


class ColumnsNeededForPatchError(PatchError):
    """Thrown when columns are required for patching values.

    It's possible to use ``pgmock.patch`` without providing columns. This is standard
    for patching anything that takes a ``VALUES`` list without associated column names
    (e.g insert into ``VALUES (...)``). However, it's illegal to not provide column
    names for patching expressions that require them.

    This error is thrown when trying to patch an expression that has a name or an
    alias associated with it and not providing the column names. For example,
    ``pgmock.patch(pgmock.table('table'), [rows])`` or patching a subquery
    without providing columns would throw this.

    This error is also thrown when trying to use lists of dictionaries as rows
    to ``pgmock.patch`` without providing column names
    """


class ColumnMismatchInPatchError(PatchError):
    """
    Thrown when creating a patch with a list of dictionaries where the dictionary keys
    don't match with the column names provided

    For example, this code will throw this error because the "col1" column is being specified
    in the row data of a patch but not the columns:

    .. code-block:: python

        pgmock.patch(pgmock.table('table'), rows=[{'col1': 'value'}], cols=['col2'])

    """


class NoConnectableError(Error):
    """Thrown when using a mock as a context manager with no connectable."""


class SideEffectExhaustedError(Error):
    """Thrown when using a side effect on a patch and the iterable has been exhausted.

    This is thrown when a ``side_effect`` has been provided for a patch, but the
    number of queries executed has surpassed the number of results in the side
    effect. For example, this code would cause this exception::

        with pgmock.mock(connectable):
            # Provide exactly one side effect result
            pgmock.patch(pgmock.table('table'),
                         side_effect=[pgmock.data(rows, cols)])

            # The first query will run fine since the side effect has one value
            run_code()

            # The second query will fail because it will try to use the second
            # value in the side effect
            run_code()
    """


class ValueSerializationError(Error):
    """Thrown when a Python value cannot be serialized to a postgres ``VALUES`` value.

    pgmock supports serializing the following Python types: bool, float,
    int, str, dict (json), UUID, datetime, date, time (all time types support timezones).

    If the python type being serialized doesn't match, one must supply
    a column type hint when patching values. Open an issue on pgmock or contact
    the authors in order to support serializing other types!
    """


def throw(exception, msg, sql=None):
    """Throws an exception with an error message that points to exception docs"""
    err_msg = msg
    if sql:
        if isinstance(sql, str):
            err_msg += ' The following SQL was used: \n\n{}\n\n'.format(sql.strip())
        elif isinstance(sql, (list, tuple)):
            err_msg += (
                ' The following multiple matches of SQL were used: \n\n{}\n\n'
            ).format('\n---\n'.join(s.strip() for s in sql))
        else:
            raise AssertionError
    else:
        err_msg += ''

    err_msg += 'View the docs for this exception at {} for more information.'.format(DOCS_URL)
    raise exception(err_msg)
