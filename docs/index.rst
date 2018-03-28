pgmock
======

``pgmock`` provides utilities for obtaining and mocking out expressions in Postgres queries. This
allows for testing smaller portions of larger queries and alleviates issues of having to
set up state in the database for more traditional (and faster) SQL unit tests.

``pgmock`` has three primary use cases:

1. Obtaining expressions in a query
2. Patching expressions in a query
3. Patching queries executed by SQLAlchemy

A quickstart for each of these is below. To skip the quickstart and go straight to the
tutorial, go to :ref:`tutorial`.

Quickstart
----------

Obtaining Expressions in a Query
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Assume we want to test the following query:

.. code-block:: python

    query = "SELECT sub.c1, sub.c2 FROM (SELECT c1, c2 FROM test_table WHERE c1 = 'hi!') sub;"

This example illustrates a query that has comparison logic in the subquery named *sub*. 
This subquery can be obtained with:

.. code-block:: python

    import pgmock

    sub = pgmock.sql(query, pgmock.subquery('sub'))

    print(sub)
    "SELECT c1, c2 FROM test_table WHERE c1 = 'hi!'"

In the above, ``pgmock.sql`` was used to render the SQL targetted by the ``pgmock.subquery`` *selector*.
A selector is a way to specify an expression inside a query. In this case, it's a subquery named *sub*.

Selectors can be chained together to refine selections. For example, ``pgmock.statement(0).subquery('sub')``
would reference the subquery ``sub`` in the first statement of the SQL. All available selectors in pgmock
are listed below. For more info about the selectors and how they work, view the :ref:`interface` section.

    1. `pgmock.statement` - Obtain a statement or range of statements
    2. `pgmock.cte` - Obtain or patch a common table expression
    3. `pgmock.create_table_as` - Obtain or patch a ``CREATE TABLE AS`` expression
    4. `pgmock.table` - Patch a table
    5. `pgmock.insert_into` - Obtain or patch an ``INSERT INTO`` expression
    6. `pgmock.subquery` - Obtain or patch a subquery

Patching Expressions in a Query
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If one wanted to test the above subquery and ensure that it filters rows properly, a database table named
``test_table`` would need to be created along with the appropriate data inserted. This setup, however, is rather
cumbersome and slow, especially in a test case that needs to tear down the database after each test.

In the spirit of `Python mocking <https://docs.python.org/3/library/unittest.mock.html>`_ and only testing logic
in unit tests, ``pgmock`` provides the ability to patch expressions with
`Postgres VALUES <https://www.postgresql.org/docs/8.2/static/sql-values.html>`_.

What does this look like in practice? Lets continue using our ``sub`` variable from above:

.. code-block:: python

    rows = [('hi!', 'val1'), ('hello!', 'val2'), ('hi!', 'val3')]

    # Patch "test_table" with the rows as the return value
    patch = pgmock.patch(pgmock.table('test_table'), rows=rows, cols=['c1', 'c2'])

    # Apply the patch to the subquery SQL
    patched = pgmock.sql(sub, patch)

    print(patched)
    "SELECT c1, c2 FROM (VALUES ('hi!','val1'),('hello!','val2'),('hi!','val3')) AS test_table(c1,c2) WHERE c1 = 'hi!'"

In the above, we made a ``patch`` with a ``table`` selector and made it return a list of rows. When using ``sql`` to
render the query, ``test_table`` was modified to be a ``VALUES`` expression.

The ``patched`` query can now be executed with no database setup and the filtering logic can be tested for correctness.

This approach could similarly be used on the full original query. Patching the table of the subquery would proceed as follows:

.. code-block:: python

    # Apply the patch to the full query
    patched = pgmock.sql(query, patch)

    print(patched)
    "SELECT sub.c1, sub.c2 FROM (SELECT c1, c2 FROM (VALUES ('hi!','val1'),('hello!','val2'),('hi!','val3')) AS test_table(c1,c2) WHERE c1 = 'hi!') sub;"

One could similarly patch out the entire subquery:

.. code-block:: python

    # Patch the "sub" subquery with the rows as the return value
    patch = pgmock.patch(pgmock.subquery('sub'), rows=rows, cols=['c1', 'c2'])

    # Apply the patch to the full query
    patched = pgmock.sql(query, patch)

    print(patched)
    "SELECT sub.c1, sub.c2 from (VALUES ('hi!','val1'),('hello!','val2'),('hi!','val3')) AS sub(c1,c2);"

Having a patched query like the above allows one to use a readonly database connection and execute the query while testing
that it behaves as expected. For example:

.. code-block:: python

    import sqlalchemy as sqla

    db_conn = sqla.create_engine('postgresql://localhost:5432/local-db')
    results = db_conn.execute(patched)

    # Assert only rows where c1 = "hi!" are returned
    assert results == [('hi!', 'val1'), ('hi!', 'val3')]

Want to only patch out some of your columns? Pass dictionaries of rows as input and ``null`` values are filled
in for everything else in the row:

.. code-block:: python

    # Patch the "sub" subquery with the dictionary rows as the return value. All missing columns will
    # be filled with nulls
    rows = [{'c1': 'hi!'}, {'c2': 'hello!'}]
    patch = pgmock.patch(pgmock.subquery('sub'), rows=rows, cols=['c1', 'c2'])

    # Apply the patch to the full query
    patched = pgmock.sql(query, patch)

    print(patched)
    "SELECT sub.c1, sub.c2 FROM  (VALUES ('hi!',null),(null,'hello!')) AS sub(c1,c2);"

Patching Queries Executed by SQLAlchemy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes it is not possible to have full control over the SQL being executed, such as when testing SQLAlchemy code.
For this case, ``pgmock`` can be used as a context manager and modify executed SQLAlchemy queries on the fly.
This functionality can be used like so:

.. code-block:: python

    # "connectable" is a SQLAlchemy engine, session, connection, or other connectable object
    with pgmock.mock(connectable) as mocker:
        # Apply patches
        mocker.patch(pgmock.subquery('sub'), rows=rows, cols=['c1', 'c2'])

        # Execute SQLAlchemy code
        ...

        # Assert that the queries were rendered
        assert len(mocker.renderings) == expected_number_of_queries

The ``renderings`` variable contains tuples of the original SQL and the modified SQL for every query executed within the context manager.
In this example, all queries are assumed to have a *sub* subquery that is patched with provided output rows. Patching can also be done
on a per-query basis, and this is described more in the :ref:`tutorial`.

Next Steps
----------

- Go to :ref:`tutorial` for a full tutorial on ``pgmock``.
- Go to :ref:`interface` for the documentation of the main ``pgmock`` interface.
- For ``pgmock`` exceptions and docs about what causes some errors, go to :ref:`exceptions`.
- It's also good to familiarize yourself with some of the known issues and future work of ``pgmock`` by going to :ref:`issues_and_future_work`.

