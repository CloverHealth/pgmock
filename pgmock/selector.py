"""
pgmock.selector
---------------

Contains the primary functionality for chainable SQL selectors
"""
import pgmock.exceptions
import pgmock.mocker
import pgmock.render


def body():
    """Obtains the body of a selector.

    When applicable, this selector returns the body of another selection.
    For example, a ``CREATE TABLE new_table AS SELECT * FROM other_table``
    has a body of ``SELECT * FROM other_table``.

    Returns:
        Selector: A chainable SQL selector.

    Examples:
        Obtain the body of a ``CREATE TABLE AS`` expression

        .. code-block:: python

            body = pgmock.sql(sql_string, pgmock.create_table_as('table').body())

        Obtain the body of an ``INSERT INTO`` expression using the syntax of
        passing multiple selectors to ``pgmock.sql``

        .. code-block:: python

            body = pgmock.sql(sql_string, pgmock.insert_into('table'), pgmock.body())

    Note:
        This selector should only be used to refine another selector, such as
        ``pgmock.create_table_as`` or ``pgmock.insert_into``. In other words, calling:

        .. code-block:: python

            body = pgmock.sql(sql_string, pgmock.body())

        will result in an error.
    """
    return Selector().body()


def statement(start, end=None):
    """Obtains a statement selector.

    Statements are naively parsed by splitting SQL based on the semicolon.
    If any semicolons exist in the comments or literal strings, this
    selector has undefined behavior.

    Args:
        start (int): The starting statement. If ``end`` is ``None``,
            obtain a single statement
        end (int, optional): The ending statement (exclusive)

    Returns:
        Selector: A chainable SQL selector.

    Raises:
        `StatementParseError`: When the statement range is invalid for the
            parsed statements.

    Examples:
        Obtain the first statement in a SQL string

        .. code-block:: python

            statement = pgmock.sql(sql_string, pgmock.statement(0))

        Obtain the second and third statements in a SQL string

        .. code-block:: python

            statement = pgmock.sql(sql_string, pgmock.statement(1, 3))
    """
    return Selector().statement(start, end=end)


def insert_into(table):
    """Obtains a selector for an ``INSERT INTO`` expression.

    Searches for ``INSERT INTO table_name(optional columns)`` and returns
    the entire statement. The body of the statement (e.g. the ``SELECT`` or anything after
    ``INSERT INTO``) can be returned by chaining the ``body()`` selector.

    Args:
        table (str): The table of the expression.

    Returns:
        Selector: A chainable SQL selector.

    Raises:
        `NoMatchError`: When the expression cannot be found during rendering.
        `MultipleMatchError`: When multiple expressions are found during rendering.

    Examples:
        Obtain the ``INSERT INTO`` of table "t"

        .. code-block:: python

            insert_into = pgmock.sql(sql_string, pgmock.insert_into('t'))

        Obtain the body of the ``INSERT INTO`` of table "t"

        .. code-block:: python

            insert_into_body = pgmock.sql(sql_string, pgmock.insert_into('t').body())

    Note:
        When patching ``INSERT INTO`` statements, the entire body of the statement after the
        ``INSERT INTO`` is patched
    """
    return Selector().insert_into(table)


def cte(alias):
    """Obtains a selector for a common table expression (CTE)

    CTEs are matched by searching for a ``WITH cte_name AS`` or for searching
    for a CTE after a comma (e.g ``WITH cte_name1 AS ..., cte_name2 AS ...``)

    Args:
        alias (str): The alias of the CTE

    Returns:
        Selector: A chainable SQL selector

    Raises:
        `NoMatchError`: When the CTE cannot be found during rendering.
        `MultipleMatchError`: When multiple CTEs are found during rendering.
        `NestedMatchError`: When nested subquery matches are found during rendering.
        `InvalidSQLError`: When enclosing parentheses for a CTE
            cannot be found.

    Examples:
        Obtain the CTE that has the alias "a"

        .. code-block:: python

            cte = pgmock.sql(sql_string, pgmock.cte('a'))
    """
    return Selector().cte(alias)


def subquery(alias):
    """Obtains a selector for a subquery

    Subqueries are matched by an alias preceeded by an enclosing
    parenthesis. Once matched, the SQL is search for the starting
    parenthesis.

    Args:
        alias (str): The alias of the subquery.

    Returns:
        Selector: A chainable SQL selector.

    Raises:
        `NoMatchError`: When the expression cannot be found during rendering.
        `MultipleMatchError`: When multiple expressions are found during rendering.
        `NestedMatchError`: When nested subquery matches are found during rendering.
        `InvalidSQLError`: When enclosing parentheses for a subquery
            cannot be found.

    Examples:
        Obtain the subquery that has the alias "a"

        .. code-block:: python

            subquery = pgmock.sql(sql_string, pgmock.subquery('a'))

    Todo:
        - Support for subqueries without an alias (e.g. after an "in" keyword)
    """
    return Selector().subquery(alias)


def table(name, alias=None):
    """Obtains a selector for a table

    Tables are matched by searching for their name and optional
    aliases after a ``FROM`` or ``JOIN`` keyword. If the table has an alias
    but the alias isn't provided, a `NoMatchError` will be thrown.

    Args:
        name (str): The name of the table (including the schema if in the query)
        alias (str, optional): The alias of the table if it exists

    Returns:
        Selector: A chainable SQL selector.

    Raises:
        `NoMatchError`: When the expression cannot be found during rendering.
        `MultipleMatchError`: When multiple expressions are found during rendering.

    Examples:
        Obtain the table with no alias that has the name "schema.table_name"

        .. code-block:: python

            table = pgmock.sql(sql_string, pgmock.table('schema.table_name'))

        Obtain the table with the name "schema.table_name" that has the alias "a"

        .. code-block:: python

            table = pgmock.sql(sql_string, pgmock.table('schema.table_name', 'a'))

    Todo:
        - Support lateral joins and other joins that have keywords after
          the ``JOIN`` keyword
    """
    return Selector().table(name, alias=alias)


def create_table_as(table):
    """Obtains a selector for a ``CREATE TABLE AS`` statement.

    Searches for ``CREATE TABLE table_name(optional columns) AS`` and returns
    the entire statement. The body of the statement (e.g. the ``SELECT`` or anything after
    ``CREATE TABLE AS``) can be returned by chaining the ``body()`` selector.

    Args:
        table (str): The name of the table as referenced in the expression

    Returns:
        Selector: A chainable SQL selector.

    Raises:
        `NoMatchError`: When the expression cannot be found during rendering.
        `MultipleMatchError`: When multiple expressions are found during rendering.

    Examples:
        Obtain the ``CREATE TABLE AS`` of table "t"

        .. code-block:: python

            ctas = pgmock.sql(sql_string, pgmock.create_table_as('t'))

        Obtain the body of the ``CREATE TABLE AS`` of table "t"

        .. code-block:: python

            ctas_body = pgmock.sql(sql_string, pgmock.create_table_as('t').body())

    Note:
        When patching ``CREATE TABLE AS`` statements, the entire body of the statement is patched
        with a ``SELECT * FROM VALUES ... AS pgmock(columns...)``. This is because it is illegal
        to do ``VALUES ... AS ...`` after a "create table as" statement.
    """
    return Selector().create_table_as(table)


class Selector(pgmock.render.Renderable):
    """A selector for targetting expressions in SQL.

    Methods can be chained to represent what is being targetted, for example a
    subquery in the first statement::

        Selector().statement(0).subquery('alias')

    Once ``patch`` is applied to a selector, a ``Mock`` object is returned and
    only ``patch`` can be chained.
    """
    @pgmock.render.Renderable.chainable_render_method
    def __getitem__(self, index):
        pass

    @pgmock.render.Renderable.chainable_render_method
    def statement(self, start, end=None):
        pass

    @pgmock.render.Renderable.chainable_render_method
    def body(self):
        pass

    @pgmock.render.Renderable.chainable_render_method
    def cte(self, alias):
        pass

    @pgmock.render.Renderable.chainable_render_method
    def insert_into(self, table):
        pass

    @pgmock.render.Renderable.chainable_render_method
    def subquery(self, alias):
        pass

    @pgmock.render.Renderable.chainable_render_method
    def table(self, table, alias=None):
        pass

    @pgmock.render.Renderable.chainable_render_method
    def create_table_as(self, table):
        pass

    def patch(self, *args, **kwargs):
        return pgmock.mocker.Mocker(renderable=self).patch(*args, **kwargs)
