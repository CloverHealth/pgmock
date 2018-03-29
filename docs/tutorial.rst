
.. _tutorial:

Tutorial
========

This tutorial is created directly from an ipython notebook. If you’d
like to interactively run this tutorial, do the following:

::

    # Go to your pgmock directory with the cloned code
    cd pgmock
    make setup
    jupyter notebook Tutorial.ipynb
    # Follow the instructions to open the notebook in your browser

The setup for this ipython notebook is below and includes the creation
of the testing database and required imports.

.. code:: ipython3

    import testing.postgresql
    import sqlalchemy
    import pgmock
    import pgmock.exceptions
    
    test_db = testing.postgresql.Postgresql()
    test_engine = sqlalchemy.create_engine(test_db.url())

Terminology and Key Concepts
----------------------------

It’s useful to understand some commonly-used terminology and key
concepts before going into the ``pgmock`` tutorial.

**Selectors** - ``pgmock`` *selectors* are objects used to obtain
portions of SQL within a query. Selectors can represent subqueries,
tables, select statements, and other types of SQL expressions. All
selectors in ``pgmock`` are chainable, meaning they can be called after
one another to refine a selection.

**Patching** - ``pgmock`` *patching* is concerned with converting SQL
select expressions or tables into postgres ``VALUES`` expressions. For
example, this statement:

::

    SELECT c1 from test_table

could have ``test_table`` patched to be:

::

    SELECT c1 from (VALUES ('hi!'),('hello!') AS test_table(c1)

Patching can also take place on joins, subqueries, ``INSERT INTO``
expressions, and other SQL expressions that allow postgres ``VALUES``.

**Rendering** - Whenever SQL is obtained from a query or modified with a
patch, it is *rendered*.

Obtaining Expressions in a Query
--------------------------------

Obtaining specific portions of a query can be useful when wanting to
execute smaller parts of your SQL or for (later in the tutorial)
patching out portions of your SQL in tests.

This part of the tutorial demonstrates obtaining expressions inside a
query using the ``pgmock.sql`` function. ``pgmock.sql`` takes a SQL
string and a selector as input. The expression in the query referenced
by the selector is then rendered and returned as a string. Uses of
different selectors to obtain expressions is shown in the following.

Obtaining Statements
~~~~~~~~~~~~~~~~~~~~

The ``pgmock.statement`` selector can be used to render ranges of
statements in a query as shown below.

.. code:: ipython3

    query = '''SELECT * from table1;
    SELECT * from table2;
    SELECT * from table3
    '''
    
    # Obtain the first statement
    print(pgmock.sql(query, pgmock.statement(0)))


.. parsed-literal::

    SELECT * from table1


.. code:: ipython3

    # Obtain the first three statements using a range of 0 - 3 (3 is the exclusive ending index)
    print(pgmock.sql(query, pgmock.statement(0, 3)))


.. parsed-literal::

    SELECT * from table1;
    SELECT * from table2;
    SELECT * from table3
    


.. code:: ipython3

    # Going out of range will throw an exception
    try:
        pgmock.sql(query, pgmock.statement(4))
    except pgmock.exceptions.StatementParseError as exc:
        print(exc)


.. parsed-literal::

    Found 3 statements. Range of [4:5] is out of bounds. The following SQL was used: 
    
    SELECT * from table1;
    SELECT * from table2;
    SELECT * from table3
    
    View the docs for this exception at https://pgmock.readthedocs.io/en/latest/exceptions.html for more information.


.. note::

    Rendering statements splits the SQL with the semicolon character. If the semicolon appears in any comments or string literals, this can interfere with obtaining statements. Use ``safe_mode=True`` to `pgmock.sql` in order to fix this issue if it happens. This comes at a performance cost, and more details can be read at `pgmock.config.set_safe_mode`.

Obtaining Subqueries
~~~~~~~~~~~~~~~~~~~~

The ``pgmock.subquery`` selector can be used to render subqueries in SQL
as shown below.

.. code:: ipython3

    query = 'SELECT sub.c1, sub.c2 FROM (SELECT * FROM test_table) sub;'
    
    # Obtain the subquery named "sub"
    print(pgmock.sql(query, pgmock.subquery('sub')))


.. parsed-literal::

    SELECT * FROM test_table


.. code:: ipython3

    # An exception will be raised if the subquery alias cannot be found
    try:
        pgmock.sql(query, pgmock.subquery('bad'))
    except pgmock.exceptions.NoMatchError as exc:
        print(exc)


.. parsed-literal::

    No subquery found for alias "bad". The following SQL was used: 
    
    SELECT sub.c1, sub.c2 FROM (SELECT * FROM test_table) sub;
    
    View the docs for this exception at https://pgmock.readthedocs.io/en/latest/exceptions.html for more information.


.. code:: ipython3

    # pgmock does not handle the case when the same subquery alias is used twice or nested
    query = 'SELECT sub.c1, sub.c2 FROM (SELECT * FROM (SELECT * FROM test_table) sub) sub;'
    
    try:
        pgmock.sql(query, pgmock.subquery('sub'))
    except pgmock.exceptions.MultipleMatchError as exc:
        print(exc)


.. parsed-literal::

    Nested matches were found in your selection. The following multiple matches of SQL were used: 
    
    SELECT * FROM test_table
    ---
    SELECT * FROM (SELECT * FROM test_table) sub
    
    View the docs for this exception at https://pgmock.readthedocs.io/en/latest/exceptions.html for more information.


.. note::

    Almost all ``pgmock`` selectors can only render exactly one match like the subquery selector above. These cases will not be illustrated for later examples. Note that there is a distinction between "rendering" selectors with ``pgmock.sql`` like above and patching them with ``pgmock.patch``. ``pgmock.patch`` supports patching multiple occurences in a selection

Obtaining Insert Into Expressions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``pgmock.insert_into`` selector can be used to render
``INSERT INTO`` expressions in SQL as shown below.

.. code:: ipython3

    query = '''INSERT INTO table_a
    SELECT * FROM other_table;
    
    INSERT INTO table_b
    SELECT * FROM other_table'''
    
    # The insert_into selector takes the table name that is inserted into
    print(pgmock.sql(query, pgmock.insert_into('table_a')))


.. parsed-literal::

    INSERT INTO table_a
    SELECT * FROM other_table


In order to obtain the body of the expression, the ``body`` selector can
be chained to the ``insert_into`` selector.

.. code:: ipython3

    print(pgmock.sql(query, pgmock.insert_into('table_a').body()))


.. parsed-literal::

    SELECT * FROM other_table


.. note::

    All selectors can be chained like the above example where it makes sense. For example, one could obtain the ``INSERT INTO`` expression of the first statement with ``pgmock.statement(0).insert_into('table_a')``
    
    Along with that, multiple selectors can also be provided to ``pgmock.sql`` or ``pgmock.sql_file``, which in turn will chain them underneath the hood. For example, doing:
    
    .. code-block:: python
    
        pgmock.sql(query, pgmock.insert_into('table_a'), pgmock.body())
        
    is equivalent to:

    .. code-block:: python
    
        pgmock.sql(query, pgmock.insert_into('table_a').body())
        
    It is up to the user to pick which style they prefer. ``pgmock`` suggests using multiple arguments when applying multiple ``pgmock.patch`` selectors and using chaining syntax for all other cases.

Obtaining Create Table As Expressions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``pgmock.create_table_as`` selector can be used to render
``CREATE TABLE AS`` expressions in SQL as shown below. It’s similar to
``pgmock.insert_into``.

.. code:: ipython3

    query = '''CREATE TABLE table_a AS (
      SELECT * FROM other_table
    );
    
    CREATE TABLE table_b AS SELECT * FROM other_table'''
    
    # The insert_into selector takes the table name that is inserted into
    print(pgmock.sql(query, pgmock.create_table_as('table_a')))


.. parsed-literal::

    CREATE TABLE table_a AS (
      SELECT * FROM other_table
    )


In order to obtain the body of the ``CREATE TABLE AS`` expression, the
``body`` selector can be chained to the ``create_table_as`` selector.

.. code:: ipython3

    print(pgmock.sql(query, pgmock.create_table_as('table_a').body()))


.. parsed-literal::

     (
      SELECT * FROM other_table
    )


Obtaining Common Table Expressions (CTEs)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``pgmock.cte`` selector can be used to render common table
expressions (CTEs) in SQL as shown below. It’s similar to
``pgmock.subquery``.

.. code:: ipython3

    query = '''
    WITH cte1 AS (
        SELECT * FROM table1
    ), cte2 AS (
        SELECT * FROM table2
    )
    '''
    
    # Obtain the CTE aliased "cte1"
    print(pgmock.sql(query, pgmock.cte('cte1')))


.. parsed-literal::

    
        SELECT * FROM table1
    


.. code:: ipython3

    # Obtain the "cte2" CTE
    print(pgmock.sql(query, pgmock.cte('cte2')))


.. parsed-literal::

    
        SELECT * FROM table2
    


Patching Expressions in a Query
-------------------------------

As mentioned before, patching parts of a query will transform the
relevant expression into `Postgres
VALUES <https://www.postgresql.org/docs/9.5/static/sql-values.html>`__.
Why is this useful?

1. When using ``VALUES`` lists, there is no need to create database
   tables and data before executing the query
2. Testing queries will run much faster in automated tests since there
   is no overhead of database setup and teardown
3. Only data that is relevant to the test can be patched, resulting in
   smaller and more readable tests. ``pgmock`` allows other useless
   columns to be filled in with nulls by default if desired

Below are some illustrations of patching queries and running some
assertions on those queries. This section uses the test engine that we
created at the beginning of the tutorial.

.. note::

    In an automated `pytest <https://docs.pytest.org/en/latest/>`_ test case, we'd use the fixtures from `pytest-pgsql <https://github.com/CloverHealth/pytest-pgsql>`_ when testing our queries

Patching Tables and Joins on Tables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tables, whether those tables are being selected or joined, can be
patched with ``pgmock`` by using the ``pgmock.table`` selector. Some
examples of patching tables and joins are below.

.. code:: ipython3

    # Create a query and filter a column
    query = "SELECT c2 FROM my_table WHERE c1 = 'value'"
    
    # Create a patch for the table. The patch takes a selector,
    # rows (a list of lists for each column or a list of dictionaries keyed on column),
    # and column names
    patch = pgmock.patch(pgmock.table('my_table'),
                         [('dummy_data', 'data'), ('value', 'hello'), ('value', 'hi')],
                         ['c1', 'c2'])
    
    # Render the patched SQL so that we can execute it
    sql = pgmock.sql(query, patch)
    print(sql)


.. parsed-literal::

    SELECT c2 FROM  (VALUES ('dummy_data','data'),('value','hello'),('value','hi')) AS my_table(c1,c2) WHERE c1 = 'value'


.. code:: ipython3

    # Execute the SQL and verify that filtering happened correctly
    results = list(test_engine.execute(sql))
    assert results == [('hello',), ('hi',)]

.. note::

    `pgmock.patch` accepts lists of dictionaries as rows of input as well. For example,
    
    .. code-block:: python
    
        patch = pgmock.patch(pgmock.table('my_table'),
                     [{'c1': 'dummy_data', 'c2': 'data'}, {'c1': 'value', 'c2': 'hello'}, {'c1': 'value', 'c2': 'hi'}],
                     ['c1', 'c2'])
                     
    is equivalent to the example from above.
    
    Using this format allows for only specifying values for columns that matter. All missing columns will be filled with null values. Both formats of patching will be used throughout the rest of the tutorial.

Similar to selectors, patches are also chainable or can be provided as
multiple arguments to ``pgmock.sql`` or ``pgmock.sql_file``. This is
useful for the case of patching multiple expressions in a query. For
example, we can patch a table and a join on another table like so.

.. code:: ipython3

    # Create a query with a join
    query = 'SELECT one.c1 FROM t1 one JOIN t2 two ON one.c1 = two.c1'
    
    # When making the patches, keep in mind these tables have aliases and
    # the alias must also be provided when obtaining the table
    t1_patch = pgmock.patch(
        pgmock.table('t1', alias='one'),
        [('val1.1',), ('val1.2',)],
        ['c1']
    )
    
    t2_patch = pgmock.patch(
        pgmock.table('t2', alias='two'),
        [('val1.1',), ('val1.2',), ('val1.3',)],
        ['c1']
    )
    
    # Render the SQL that has both tables patched
    sql = pgmock.sql(query, t1_patch, t2_patch)
    print(sql)


.. parsed-literal::

    SELECT one.c1 FROM  (VALUES ('val1.1'),('val1.2')) AS one(c1) JOIN  (VALUES ('val1.1'),('val1.2'),('val1.3')) AS two(c1) ON one.c1 = two.c1


.. code:: ipython3

    # Execute the SQL and verify that the join happened correctly
    results = list(test_engine.execute(sql))
    assert results == [('val1.1',), ('val1.2',)]

Patching Multiple Occurrences of Tables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If a table appears multiple times in your SQL, it will be patched in all
occurrences by default. This holds true for any selector. If you want to
only patch a specific occurrence or range of tables, use list syntax.
For example:

.. code:: ipython3

    # Create a query and filter a column
    query = "SELECT c2 FROM my_table; SELECT c3 from my_table"
    
    # Patch both occurrences of the table
    patch = pgmock.patch(pgmock.table('my_table'),
                         [('dummy_data', 'data'), ('value', 'hello'), ('value', 'hi')],
                         ['c2', 'c3'])
    
    # Render the patched SQL so that we can execute it
    sql = pgmock.sql(query, patch)
    print(sql)
    
    # Use list syntax to only patch the second occurrence of the table
    patch = pgmock.patch(pgmock.table('my_table')[1],
                         [('dummy_data', 'data'), ('value', 'hello'), ('value', 'hi')],
                         ['c2', 'c3'])
    print(pgmock.sql(query, patch))


.. parsed-literal::

    SELECT c2 FROM  (VALUES ('dummy_data','data'),('value','hello'),('value','hi')) AS my_table(c2,c3); SELECT c3 from  (VALUES ('dummy_data','data'),('value','hello'),('value','hi')) AS my_table(c2,c3)
    SELECT c2 FROM my_table; SELECT c3 from  (VALUES ('dummy_data','data'),('value','hello'),('value','hi')) AS my_table(c2,c3)


Patching Subqueries
~~~~~~~~~~~~~~~~~~~

Patching subqueries (and almost all other expressions) works in the same
way as patching tables. Create a selector you want to patch and provide
the data to be patched.

.. code:: ipython3

    # Create a query with a subquery
    query = "SELECT sub.c1, sub.c2 FROM (SELECT * FROM test_table) sub;"
    
    # Create a patch for the subquery. Similar to patching tables, provide a subquery selector and the data for the subquery
    patch = pgmock.patch(pgmock.subquery('sub'),
                         [('val1', 'val2'), ('val3', 'val4')],
                         ['c1', 'c2'])
    
    # Render the patched SQL so that we can execute it
    sql = pgmock.sql(query, patch)
    print(sql)


.. parsed-literal::

    SELECT sub.c1, sub.c2 FROM  (VALUES ('val1','val2'),('val3','val4')) AS sub(c1,c2);


.. code:: ipython3

    # Execute the SQL and verify that the subquery was patched properly
    results = list(test_engine.execute(sql))
    assert results == [('val1', 'val2'), ('val3', 'val4')]

Patching CTEs, Create Table As, Insert Into, and Other Expressions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``pgmock`` can patch almost every selector available in the library,
such as ``pgmock.insert_into``, ``pgmock.create_table_as``, and
``pgmock.cte``. Patching these expressions result in different types of
patches depending on what is being patched.

For example, patching an ``INSERT INTO`` statement will result in
replacing the body of the ``INSERT INTO`` with a ``VALUES`` list that
has no alias (Postgres doesn’t support the syntax of
``INSERT INTO table (VALUES ..) AS ...``).

When patching ``CREATE TABLE AS`` or a CTE, the patch will insert a
``SELECT * FROM (VALUES ...) AS ...``. Doing this syntax allows column
names of the patch to be preserved and gets around the restriction of
not being able to do ``CREATE TABLE AS (VALUES ...) AS ...``.

.. note::

    Keep in mind that when patching statements when the table structure is defined, such as ``CREATE TABLE t(col1, col2) AS`` or ``WITH cte_name(col1, col2) AS``, the columns provided to the patch need to be in the same order as they are defined in the alias definition.

Below is an example of patching a CTE

.. code:: ipython3

    # Create an example of selecting from a CTE
    query = '''
    WITH cte_name AS (
        SELECT * from some_other_table
    )
    
    SELECT c1, c2, c3 from cte_name;
    '''
    
    # Patch the CTE with the data you want returned
    patch = pgmock.patch(
        pgmock.cte('cte_name'),
                   [('val1', 'val2', 'val3')],
                   ['c1', 'c2', 'c3']
    )
    
    sql = pgmock.sql(query, patch)
    print(sql)


.. parsed-literal::

    
    WITH cte_name AS ( SELECT * FROM (VALUES ('val1','val2','val3')) AS pgmock(c1,c2,c3))
    
    SELECT c1, c2, c3 from cte_name;
    


.. code:: ipython3

    results = list(test_engine.execute(sql))
    assert results == [('val1', 'val2', 'val3')]

Patching and Executing Smaller Components of Queries
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes one may only be interested in testing a small part of their
SQL. This is especially true in testing the selects of an
``INSERT INTO`` or a subquery. An example of pulling out a subquery and
testing it is shown below.

.. code:: ipython3

    # Create a query with a subquery
    query = "SELECT sub.c1, sub.c2 FROM (SELECT * FROM test_table where c1 = 'value') sub;"
    
    # Obtain the subquery so that it can be patched and tested
    subquery = pgmock.sql(query, pgmock.subquery('sub'))
    
    # Create a patch for the subquery's table. Similar to patching tables, provide a subquery selector and the data for the subquery
    patch = pgmock.patch(pgmock.table('test_table'),
                         [('value', 'val2'), ('val3', 'val4')],
                         ['c1', 'c2'])
    
    # Render the patched SQL so that we can execute it
    sql = pgmock.sql(subquery, patch)
    print(sql)


.. parsed-literal::

    SELECT * FROM  (VALUES ('value','val2'),('val3','val4')) AS test_table(c1,c2) where c1 = 'value'


.. code:: ipython3

    # Execute the SQL and verify that the subquery performs its select properly
    results = list(test_engine.execute(sql))
    assert results == [('value', 'val2')]

Patching Queries Executed by SQLAlchemy
---------------------------------------

Sometimes it’s not always possible to have full control of the SQL
that’s being executed. For example, one might want to test code that
issues many different SQLAlchemy statements and still want to patch out
the underlying tables.

For these cases, ``pgmock.mock`` can be used as a context manager.
``pgmock.mock`` takes the SQLAlchemy connectable as an argument and
listens for any queries executed against the connectable. When queries
are executed, they are patched on the fly before they are executed. Some
examples of this are shown below.

.. code:: ipython3

    with pgmock.mock(test_engine) as mocker:
        # Apply patches to the mocker object we created. For this example, we are going to
        # patch "test_table"
        mocker.patch(pgmock.table('test_table'), [('val1', 'val2', 'val3')], ['c1', 'c2', 'c3'])
        
        # When executing this query, it will be patched on the fly with the values provided
        results = list(test_engine.execute('SELECT * from test_table'))
        assert results == [('val1', 'val2', 'val3')]

Patching Multiple Queries with Side Effects
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In most testing situations, one will have more complex SQLAlchemy code
that may issue multiple queries. For example, lets take the previous
test example and put our SQLAlchemy code in a function that executes two
different queries.

.. code:: ipython3

    def my_sqla_func(engine):
        """A function that issues a couple different queries that we want to test"""
        cursors = engine.execute('SELECT * from pg_cursors')
        # Do something important with the cursors...
        
        # Now return results from a table
        return list(engine.execute('SELECT * from test_table'))

If we try to test this function the same way as before, an error will
happen.

.. code:: ipython3

    with pgmock.mock(test_engine) as mocker:
        # Apply patches to the mocker object we created. For this example, we are going to
        # patch "test_table"
        mocker.patch(pgmock.table('test_table'), [('val1', 'val2', 'val3')], ['c1', 'c2', 'c3'])
        
        # When executing this query, it will be patched on the fly with the values provided
        try:
            results = my_sqla_func(test_engine)
            assert results == [('val1', 'val2', 'val3')]
        except pgmock.exceptions.NoMatchError as exc:
            print(exc)


.. parsed-literal::

    No table "test_table" found. The following SQL was used: 
    
    SELECT * from pg_cursors
    
    View the docs for this exception at https://pgmock.readthedocs.io/en/latest/exceptions.html for more information.


In the above, running ``my_sqla_func`` with the patched “test_table”
threw a ``NoMatchError``. When looking at the error message, it appears
that this error occurred on our first query of our function
(``SELECT * from pg_cursors``).

This happens because the patch on “test_table” will be applied to every
single query that’s issued, including the first query that cannot be
patched. Instead of silently continuing, ``pgmock`` will raise errors
anytime something cannot be matched.

In order to get around this, use a ``side_effect`` argument to the patch
instead of a single return value. A side effect is a list of return
values to use every time the patch is applied to a query. The first side
effect will be applied to the first query issued and so forth. If more
queries are issued than the number of side effects, a
``SideEffectExhaustedError`` will be raised. If ``None`` is provided as
a return value, the patch will be completely ignored for the query.

The previous example can be changed to use a side effect in the
following way.

.. code:: ipython3

    with pgmock.mock(test_engine) as mocker:
        # Apply patches to the mocker object we created. For this example, we are going to
        # patch "test_table" on the second query that is issued by using a side effect
        mocker.patch(
            pgmock.table('test_table'),
            side_effect=[
                # Ignore patching test_table for the first query
                None,
                # Use pgmock.data to construct rows and columns of return data for
                # the second query
                pgmock.data([('val1', 'val2', 'val3')], ['c1', 'c2', 'c3'])
            ])
        
        # When executing this query, it will be patched on the fly with the values provided
        results = my_sqla_func(test_engine)
        assert results == [('val1', 'val2', 'val3')]
        
        # As a precaution, it is always good practice to assert that the number of renderings of
        # the mocker matches the number of queries you expected your test code to issue
        assert len(mocker.renderings) == 2

Advanced Usage
--------------

Patching Custom Types and Using Type Hinting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``pgmock`` allows the user to provide quite a few different types of
Python objects to patched values lists. Python objects are converted
into their proper postgres type. For example, a datetime object is
converted to a timestamp and a dictionary is converted to a json object.
An example of this is shown below.

.. code:: ipython3

    import datetime as dt
    query = "SELECT * FROM my_table"
    
    # Create a patch for the table. The patch takes a selector, rows (a list of lists for each column), and column names
    patch = pgmock.patch(pgmock.table('my_table'),
                         [(dt.datetime(2017, 6, 14), {'my': 'json_data'}, None)],
                         ['c1', 'c2', 'c3'])
    
    # Render the patched SQL so that we can execute it
    sql = pgmock.sql(query, patch)
    print(sql)


.. parsed-literal::

    SELECT * FROM  (VALUES ('2017-06-14T00:00:00'::TIMESTAMP,'{"my": "json_data"}'::JSON,null)) AS my_table(c1,c2,c3)


The amount of Python types supported out of the box in ``pgmock`` is
rather limited. Along with that, it’s impossible to specify certain
datatypes one might need for their tests in Python (e.g. a null
datetime). ``pgmock`` allows the user to specify type hints to cast
their values to a particular type. The type is specified by placing
``::type_name`` after the column name. For example, the following
illustrates how to cast patched values to datetimes and bigints.

.. code:: ipython3

    # Create a patch for the table. The patch takes a selector, rows (a list of lists for each column), and column names
    patch = pgmock.patch(pgmock.table('my_table'),
                         [('2017, 6, 14', 10000, None)],
                         ['c1::timestamp', 'c2::bigint', 'c3::timestamp'])
    
    # Render the patched SQL so that we can execute it
    sql = pgmock.sql(query, patch)
    print(sql)


.. parsed-literal::

    SELECT * FROM  (VALUES ('2017, 6, 14'::timestamp,10000::bigint,null::timestamp)) AS my_table(c1,c2,c3)


.. note::

    Type hints can only be used on python strings, floats, and ints. In other words, if you use a "timestamp" type, a string must be used as the value instead of a datetime object. Otherwise a ``ColumnTypeError`` will be raised.

Testing Postgres Arrays
~~~~~~~~~~~~~~~~~~~~~~~

Postgres arrays can be modeled in pgmock but cannot be passed in as
python lists instead they must be strings in the Postgres array syntax.
The syntax is similar to python except for curly brackets. If it’s a
text array then each string should be surrounded by double quotes.
Remember to cast the field as the correct array type (ex. ::text[] or
integer[]).

.. code:: ipython3

    # Create a patch for the table. The patch takes a selector, rows (a list of lists for each column), and column names
    patch = pgmock.patch(pgmock.table('my_table'),
                         [('2017, 6, 14', 10000, '{"apple", "iphone"}')],
                         ['c1::timestamp', 'c2::bigint', 'c3::text[]'])
    
    # Render the patched SQL so that we can execute it
    sql = pgmock.sql(query, patch)
    print(sql)


.. parsed-literal::

    SELECT * FROM  (VALUES ('2017, 6, 14'::timestamp,10000::bigint,'{"apple", "iphone"}'::text[])) AS my_table(c1,c2,c3)


Filling in Meaningless Columns with nulls
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes the logic in a query only depends on the values of a couple
columns and it isn’t necessary to provide values for all of the other
columns. ``pgmock`` allows users to ignore providing values for columns
and fills in the empty values with null. Below is an example that
illustrates how to do this when passing in rows to ``pgmock.patch``.

.. code:: ipython3

    # Create a query that returns many columns
    query = "SELECT c1, c2, c3, c4, c5 from test_table where c1 = 'value'"
    
    # When patching out the table, only provide values for "c1" since we're testing the filtering of the select
    patch = pgmock.patch(pgmock.table('test_table'), [('value', ), ('not_filtered', )], ['c1', 'c2', 'c3', 'c4', 'c5'])
    
    # Render the patched SQL. All other values for columns will be null
    sql = pgmock.sql(query, patch)
    print(sql)


.. parsed-literal::

    SELECT c1, c2, c3, c4, c5 from  (VALUES ('value',null,null,null,null),('not_filtered',null,null,null,null)) AS test_table(c1,c2,c3,c4,c5) where c1 = 'value'


.. code:: ipython3

    # The patch can also take a list of dictionaries that only specifies which column values to use. This is another
    # way to fill in meaningless values with nulls
    patch = pgmock.patch(pgmock.table('test_table'), [{'c1': 'value'}, {'c1': 'not_filtered'}], ['c1', 'c2', 'c3', 'c4', 'c5'])
    
    # Render the patched SQL. All other values for columns will be null
    sql = pgmock.sql(query, patch)
    print(sql)


.. parsed-literal::

    SELECT c1, c2, c3, c4, c5 from  (VALUES ('value',null,null,null,null),('not_filtered',null,null,null,null)) AS test_table(c1,c2,c3,c4,c5) where c1 = 'value'


.. code:: ipython3

    # Only one row should have matched the filter
    results = list(test_engine.execute(sql))
    assert len(results) == 1

.. code:: ipython3

    # Be sure to stop the testing DB for this tutorial
    test_db.stop()
    test_engine.dispose()

Configuring for Accuracy and Performance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``pgmock`` comes with a configuration module (``pgmock.config``) that
can be used to set flags that aid in accuracy of selectors / patching.
These flags come with accuracy/performance hits that should be known
before using them.

Safe Mode
^^^^^^^^^

``pgmock`` searches SQL with regular expressions. Regular expressions
can get tripped up whenever special characters appear in comments of SQL
or in string literals. For example, ``-- this is my comment; hello!``
will mess up ``pgmock.statement`` since it splits the SQL by the
semicolon character. Turning on **safe mode** will search a
pre-formatted version of the supplied SQL that is stripped of comments
and string literals.

Safe mode can be turned on with ``pgmock.config.set_safe_mode``. By
default, it is set to ``False`` because it incurs a major performance
hit when using it. Safe mode doesn’t have to be configured globally with
``pgmock.config.set_safe_mode``. It can be passed to ``pgmock.sql`` or
``pgmock.sql_file`` as an argument. It can also be used in a context
manager so that it is only set during the duration of execution like so:

.. code:: ipython3

    with pgmock.config.set_safe_mode(True):
        # Run SQL that cant natively be searched by pgmock because of regex issues
        ...

It’s recommended to pass it as an argument to ``pgmock.sql`` when
needing to be modified. For configuring it in a pytest fixture, one can
use the context manager like so:

.. code:: ipython3

    import pytest
    
    @pytest.fixture(scope='module')
    def use_safe_mode():
        with pgmock.config.set_safe_mode(True):
            yield

Replace New Patch Aliases
^^^^^^^^^^^^^^^^^^^^^^^^^

Since ``pgmock`` turns expressions into ``VALUES`` expressions when
patching, it is not always possible to preserve the original name of
what’s being patched. For example, ``SELECT * from schema.table_name``
is impossible to patch as
``SELECT * FROM (VALUES ...) AS schema.table_name`` since
``schema.table_name`` is not a valid alias.

When this case happens in the case of the ``pgmock.table`` selector,
``pgmock`` will make an alias as the table name and then replace any
refences to the old table name.

For example, ``SELECT schema.table_name.col FROM schema.table_name``
would be replaced with
``SELECT table_name.col FROM (VALUES ...) AS table_name(...)``. Note
that this only matters when the full schema and table name is used to
reference columns.

By default, this mode is turned on. To turn it off globally, call
``pgmock.config.set_replace_new_patch_aliases(False)``. Similar to
``pgmock.config.set_safe_mode``, this function can be used as a context
manager or in a pytest fixture. It can also be given as an argument to
``pgmock.mock`` since SQLAlchemy will use this style of selects by
default when making a ``sqlalchemy.insert`` object from a table with a
schema.

If users are never using the full schema and table name when referencing
columns, it is safe to turn this option off and will improve
``pgmock.table`` selector performance by about 20%.

Using pgmock with pytest
------------------------

The examples above illustrate programmatically making a test database
and running assertions. For examples of how to use ``pgmock`` with
pytest, check out the `test_examples.py
file <https://github.com/CloverHealth/pgmock/blob/master/pgmock/tests/test_examples.py>`__
in ``pgmock``. This file shows how to use ``pgmock`` with
`pytest-pgsql <https://github.com/CloverHealth/pytest-pgsql>`__. An
example of using the context manager and reading from a SQL file is
provided.
