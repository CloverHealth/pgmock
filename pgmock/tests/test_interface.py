"""Tests the primary interface of pgmock.

Examples of using the main pgmock interface should be able
to be derived from this test file as well. These tests contain both
unit-style tests and integration tests that hit a database.

Any pure unit tests for modules goes in the respective test_{module}
file
"""
import datetime as dt

import pytest
import sqlalchemy as sqla

import pgmock
import pgmock.exceptions


def test_sql_file(tmpdir):
    """Tests rendering sql from a file"""
    sql_file = tmpdir.join('sql_file.sql')
    sql_file.write('select bb.c1, bb.c2 from (select * from test_table) bb;')

    assert pgmock.sql_file(str(sql_file), pgmock.subquery('bb')) == 'select * from test_table'


def test_sql_file_no_selector(tmpdir):
    """Tests rendering sql from a file when no selector is given"""
    sql_file = tmpdir.join('sql_file.sql')
    sql = 'select bb.c1, bb.c2 from (select * from test_table) bb;'
    sql_file.write(sql)

    assert pgmock.sql_file(str(sql_file)) == sql


@pytest.mark.parametrize('query, start, end, expected', [
    ('select * from a; select * from b; select * from c', 0, None, 'select * from a'),
    ('select * from a;select * from b; select * from c', 1, 3, 'select * from b; select * from c'),
    pytest.mark.xfail(
        ('select * from a;select * from b; select * from c', 1, 4, None),
        raises=pgmock.exceptions.StatementParseError)
])
def test_statement(query, start, end, expected):
    """Tests obtaining statements from a query"""
    sql = pgmock.sql(query, pgmock.statement(start, end))
    assert sql == expected


@pytest.mark.parametrize('sql, selectors, expected_sql', [
    (
        'select * from a; select * from b; select * from c',
        [pgmock.statement(0), pgmock.table('a')],
        'a'
    ),
    (
        'select * from a; select * from b; select * from c',
        [pgmock.statement(0).table('a')],
        'a'
    ),
    (
        'select * from a; select * from b; select * from c',
        [pgmock.patch(pgmock.table('b'), [[1]], ['c1']),
         pgmock.patch(pgmock.table('c'), [[1]], ['c1'])],
        (
            'select * from a; select * from  (VALUES (1)) AS b("c1");'
            ' select * from  (VALUES (1)) AS c("c1")'
        )
    ),
    (
        'select * from a; select * from b; select * from c',
        [pgmock.patch(
            pgmock.table('b'), [[1]], ['c1']).patch(
                pgmock.table('c'), [[1]], ['c1'])],
        (
            'select * from a; select * from  (VALUES (1)) AS b("c1");'
            ' select * from  (VALUES (1)) AS c("c1")'
        )
    ),
    pytest.mark.xfail((
        'select * from a; select * from b; select * from c',
        [pgmock.patch(pgmock.table('b'), [[1]], ['c1']),
         pgmock.table('c')],
        None,
    ), raises=pgmock.exceptions.SelectorChainingError)
])
def test_chaining(sql, selectors, expected_sql):
    """
    Ensures that selectors can either be chained or passed in separately
    (which will chain them underneath the hood)
    """
    assert pgmock.sql(sql, *selectors) == expected_sql


@pytest.mark.parametrize('query, alias, expected_select', [
    pytest.mark.xfail(
        ('select b.c1, b.c2 from (select * from test_table) bb;', 'b', None),
        raises=pgmock.exceptions.NoMatchError),
    pytest.mark.xfail(
        ('select * from (select * from (select * from test_table) bb) bb;', 'bb', None),
        raises=pgmock.exceptions.MultipleMatchError),
    ('select bb.c1, bb.c2 from (select * from test_table) bb;', 'bb', 'select * from test_table'),
    ('select b.c1, b.c2 from (select * from test_table) AS b;', 'b', 'select * from test_table'),
    pytest.mark.xfail(
        ('select NOW() as c from t; select c.c1 from (select * from test_table) AS c;', 'c', None),
        raises=pgmock.exceptions.MultipleMatchError),
])
def test_subquery(query, alias, expected_select):
    """Tests getting a subquery from an SQL statement"""
    sql = pgmock.sql(query, pgmock.subquery(alias))
    assert sql == expected_select


@pytest.mark.parametrize('query, alias', [
    ('select bb.c1, bb.c2 from (select * from test_table) bb;', 'bb'),
    ('select c.c1, c.c2 from (select * from (\nselect * from t)bb) c;', 'bb'),
    ('select c.c1, c.c2 from (select * from (\nselect * from t)bb) c;', 'bb'),
    pytest.mark.xfail(('select * from \nselect * from t)bb) c;', 'bb'),
                      raises=pgmock.exceptions.InvalidSQLError),
])
def test_subquery_patch(transacted_postgresql_db, query, alias):
    """Tests patching a subquery"""
    patch = pgmock.patch(pgmock.subquery(alias),
                         [('val1.1', 'val2.1'), ('val1.2', 'val2.2')],
                         ['c1', 'c2'])
    sql = pgmock.sql(query, patch)

    res = transacted_postgresql_db.connection.execute(sql)
    assert list(res) == [('val1.1', 'val2.1'), ('val1.2', 'val2.2')]


@pytest.mark.parametrize('sql, selector, safe_mode, expected', [
    pytest.mark.xfail(
        ("select bb.c1, bb.c2 from (select * from t where c1 = ')') bb;",
         pgmock.subquery('bb'),
         False,
         None),
        raises=pgmock.exceptions.InvalidSQLError
    ),
    ("select bb.c1, bb.c2 from (select * from t where c1 = ')') bb;",
     pgmock.subquery('bb'),
     True,
     "select * from t where c1 = ')'"),
    pytest.mark.xfail(
        ("-- insert into table blah\ninsert into table blah;",
         pgmock.insert_into('table'),
         False,
         None),
        raises=pgmock.exceptions.MultipleMatchError
    ),
    ("-- insert into table blah\ninsert into table blah;",
     pgmock.insert_into('table'),
     True,
     'insert into table blah')
])
def test_safe_mode(sql, selector, safe_mode, expected):
    """Tests various selections with safe mode on and off"""
    sql = pgmock.sql(sql, selector, safe_mode=safe_mode)
    assert sql == expected


@pytest.mark.parametrize('query, alias, expected_select', [
    pytest.mark.xfail(
        ('select b.c1, b.c2 from (select * from test_table) bb;', 'b', None),
        raises=pgmock.exceptions.NoMatchError),
    pytest.mark.xfail(
        ('WITH bb AS (SELECT * FROM a), bb AS (SELECT * FROM c)', 'bb', None),
        raises=pgmock.exceptions.MultipleMatchError),
    ('WITH bb AS (SELECT * FROM test_table)', 'bb', 'SELECT * FROM test_table'),
    ('WITH bb AS (SELECT * FROM test_table)', 'bb', 'SELECT * FROM test_table'),
    ('WITH a AS (), b AS (SELECT b.c1, b.c2 from d);', 'b', 'SELECT b.c1, b.c2 from d'),
    ('WITH a AS (), b AS (WITH d AS (SELECT b.c1, b.c2 from d));', 'd',
     'SELECT b.c1, b.c2 from d'),
])
def test_cte(query, alias, expected_select):
    """Tests getting a CTE from an SQL statement"""
    sql = pgmock.sql(query, pgmock.cte(alias))
    assert sql == expected_select


@pytest.mark.parametrize('query, alias', [
    ('WITH a AS (select bb.c1, bb.c2 from table) SELECT * from a', 'a'),
    ('WITH a(c1, c2) AS (select bb.c1, bb.c2 from table) SELECT * from a', 'a'),
    ('WITH b AS (SELECT * FROM (VALUES (1)) AS bb), a AS (select * from t) SELECT * from a', 'a'),
])
def test_cte_patch(transacted_postgresql_db, query, alias):
    """Tests patching a CTE"""
    patch = pgmock.patch(pgmock.cte(alias),
                         [('val1.1', 'val2.1'), ('val1.2', 'val2.2')],
                         ['c1', 'c2'])
    sql = pgmock.sql(query, patch)

    res = transacted_postgresql_db.connection.execute(sql)
    assert list(res) == [('val1.1', 'val2.1'), ('val1.2', 'val2.2')]


@pytest.mark.parametrize('query, table, alias, values', [
    ('select t1.c1 from t1', 't1', None, [('val1.1',), ('val1.2',)]),
    ('select t1.c1 from t1', 't1', None, []),
    ('select t1.c1 from t1 where c1 = 1::text', 't1', None, []),
    ('select a.c1 from t1 AS a', 't1', 'a', [('val1.1',), ('val1.2',)]),
    ('select t1.c1 from schema.t1', 'schema.t1', None, [('val1.1',), ('val1.2',)]),
    ('select schema.t1.c1 from schema.t1', 'schema.t1', None, [('val1.1',), ('val1.2',)]),
    ('select s.c1 from schema.t1 AS s', 'schema.t1', 's', [('val1.1',), ('val1.2',)]),
    pytest.mark.xfail(
        ('select a.c1 from t1 AS a', 't1', 'b', [('val1.1',), ('val1.2',)]),
        raises=pgmock.exceptions.NoMatchError),
    ('select t1.c1 from t1; select t1.c1 from t1', 't1', None, [('val1.1',), ('val1.2',)])
])
def test_table_patch(transacted_postgresql_db, query, table, alias, values):
    """Tests patching tables when selecting"""
    patch = pgmock.patch(pgmock.table(table, alias=alias),
                         values,
                         ['c1'])
    sql = pgmock.sql(query, patch)

    res = transacted_postgresql_db.connection.execute(sql)
    assert list(res) == values


@pytest.mark.parametrize('sql, selector', [
    (
        'select * from (select * from (select * from test_table) bb) bb;',
        pgmock.patch(pgmock.subquery('bb'), None),
    )
])
def test_nested_selection(transacted_postgresql_db, sql, selector):
    """Verifies that nested selections result in an error"""
    with pytest.raises(pgmock.exceptions.NestedMatchError):
        pgmock.sql(sql, selector)


@pytest.mark.parametrize('sql, selector, expected_sql', [
    (
        'select * from t1 union all select * from t1',
        pgmock.patch(pgmock.table('t1')[0], [('val1.1',), ('val1.2',)], ['c1']),
        "select * from  (VALUES ('val1.1'),('val1.2')) AS t1(\"c1\") union all select * from t1"
    ),
    (
        'select * from t1 union all select * from t1',
        pgmock.patch(pgmock.table('t1')[1], [('val1.1',), ('val1.2',)], ['c1']),
        "select * from t1 union all select * from  (VALUES ('val1.1'),('val1.2')) AS t1(\"c1\")"
    ),
    (
        'select * from t1 union all select * from t1',
        pgmock.patch(pgmock.table('t1')[:], [('val1.1',), ('val1.2',)], ['c1']),
        ("select * from  (VALUES ('val1.1'),('val1.2')) AS t1(\"c1\") union all"
         " select * from  (VALUES ('val1.1'),('val1.2')) AS t1(\"c1\")")
    ),
    (
        'insert into a select * from t; insert into a select * from t',
        pgmock.patch(pgmock.insert_into('a')[0], [('val1.1',), ('val1.2',)], ['c1']),
        "insert into a  VALUES ('val1.1'),('val1.2'); insert into a select * from t"
    ),
    pytest.mark.xfail((
        'insert into a select * from t; insert into a select * from t',
        pgmock.patch(pgmock.insert_into('a').body(), [('val1.1',), ('val1.2',)], ['c1']),
        None
    ), raises=pgmock.exceptions.MultipleMatchError),
    (
        'select * from (select * from t) bb;select * from (select * from t) bb;',
        pgmock.patch(pgmock.subquery('bb'), [('val1.1',), ('val1.2',)], ['c1']),
        ("select * from  (VALUES ('val1.1'),('val1.2')) AS bb(\"c1\");"
         "select * from  (VALUES ('val1.1'),('val1.2')) AS bb(\"c1\");")
    ),
    (
        'create table a as (select * from t); create table a as (select * from t)',
        pgmock.patch(pgmock.create_table_as('a'), [('val1.1',), ('val1.2',)], ['c1']),
        ("create table a as SELECT * FROM (VALUES ('val1.1'),('val1.2')) AS pgmock(\"c1\");"
         " create table a as SELECT * FROM (VALUES ('val1.1'),('val1.2')) AS pgmock(\"c1\")")
    ),
    (
        'WITH bb AS (SELECT * FROM a), bb AS (SELECT * FROM c)',
        pgmock.patch(pgmock.cte('bb'), [('val1.1',), ('val1.2',)], ['c1']),
        ("WITH bb AS ( SELECT * FROM (VALUES ('val1.1'),('val1.2')) AS pgmock(\"c1\")),"
         " bb AS ( SELECT * FROM (VALUES ('val1.1'),('val1.2')) AS pgmock(\"c1\"))")
    )
])
def test_multiple_match_patching(transacted_postgresql_db, sql, selector, expected_sql):
    """Tests patching occurences of multiple matches"""
    sql = pgmock.sql(sql, selector)
    assert sql == expected_sql


@pytest.mark.parametrize('query, table, table_alias, join, join_alias', [
    ('select t1.c1 from t1 join t2 on t1.c1 = t2.c1', 't1', None, 't2', None),
    ('select one.c1 from t1 one join t2 two on one.c1 = two.c1', 't1', 'one', 't2', 'two'),
])
def test_multi_table_patch(transacted_postgresql_db, query, table, table_alias, join, join_alias):
    """Tests patching tables when selecting and joining"""
    cols = ['c1']
    patch = pgmock.patch(
        pgmock.table(table, alias=table_alias),
        [('val1.1',), ('val1.2',)],
        cols)
    patch = patch.patch(
        pgmock.table(join, alias=join_alias),
        [('val1.1',), ('val1.2',), ('val1.3',)],
        cols)
    sql = pgmock.sql(query, patch)

    res = transacted_postgresql_db.connection.execute(sql)
    assert list(res) == [('val1.1',), ('val1.2',)]


def test_select_schema_table_col_from_table_patch(transacted_postgresql_db):
    """Tests the case of selecting a schema.table.column and patching it"""
    sql = 'SELECT schema.table_name.col1 from schema.table_name'
    patch = pgmock.patch(
        pgmock.table('schema.table_name'),
        [('val1.1',), ('val1.2',), ('val1.3',)],
        ['col1'])
    sql = pgmock.sql(sql, patch)

    res = transacted_postgresql_db.connection.execute(sql)
    assert list(res) == [('val1.1',), ('val1.2',), ('val1.3',)]


@pytest.mark.parametrize('query, table, expected', [
    (' insert into a select * from t; select * from b', 'a', 'insert into a select * from t'),
    (' insert into a select * from t ', 'a', 'insert into a select * from t '),
    (' insert into a\n\n --comment\n select * from t ', 'a',
     'insert into a\n\n --comment\n select * from t '),
    (' insert into a\n\n /*comment*/\n select * from t ', 'a',
     'insert into a\n\n /*comment*/\n select * from t '),
    (' insert into a(my, cols) select * from t', 'a',
     'insert into a(my, cols) select * from t'),
    (' insert into a (my, cols) select * from t', 'a',
     'insert into a (my, cols) select * from t'),
    pytest.mark.xfail(
        ("select * from t where i = ';'", 'a', None), raises=pgmock.exceptions.NoMatchError),
    pytest.mark.xfail(
        ('insert into a select * from t; insert into a select * from t', 'a', None),
        raises=pgmock.exceptions.MultipleMatchError)
])
def test_insert_into(query, table, expected):
    """Tests getting an "insert into" statement from a query"""
    sql = pgmock.sql(query, pgmock.insert_into(table))
    assert sql == expected


@pytest.mark.parametrize('query, table', [
    (' insert into a select * from t; select * from b', 'a'),
    (' insert into a select * from t ', 'a'),
    (' insert into a ( select * from t )', 'a'),
    (' insert into a ( select * from t );', 'a'),
    (" insert into a select * from t where i = ';'", 'a'),
])
def test_insert_into_patched(query, table):
    """Tests patching an "insert into" statement from a query"""
    sql = pgmock.sql(query, pgmock.insert_into(table).patch(rows=[(1,), (2,)],
                                                            cols=['a']))
    assert sql == 'insert into a  VALUES (1),(2)'


@pytest.mark.parametrize('query, table, expected', [
    (' create table a as ( select * from t ) ; select * from b', 'a',
     'create table a as ( select * from t ) '),
    (' create table a as ( select * from t )', 'a', 'create table a as ( select * from t )'),
    (' create table a as\n select * from t', 'a', 'create table a as\n select * from t'),
    (' create table a as\n--comment\n select * from t', 'a',
     'create table a as\n--comment\n select * from t'),
    pytest.mark.xfail(
        (" create table a as(select * from t where i = ';')", 'a',
         "create table a as(select * from t where i = ';')")),
    (' create table a as(select * from t)', 'a',
     'create table a as(select * from t)'),
    (' create table a(has, columns)as(select * from t)', 'a',
     'create table a(has, columns)as(select * from t)'),
    (' create table a  (has, columns)   \nas(select * from t)', 'a',
     'create table a  (has, columns)   \nas(select * from t)'),
    pytest.mark.xfail(
        ("select * from t where i = ';'", 'a', None), raises=pgmock.exceptions.NoMatchError),
    pytest.mark.xfail(
        ('create table a as (select * from t); create table a as (select * from t)', 'a', None),
        raises=pgmock.exceptions.MultipleMatchError)
])
def test_create_table_as(query, table, expected):
    """Tests getting an "create table as" statement from a query"""
    sql = pgmock.sql(query, pgmock.create_table_as(table))
    assert sql == expected


@pytest.mark.parametrize('query, table', [
    (' create table a as (select * from t); select * from b', 'a'),
    (' create table a as (select * from t )', 'a'),
    (" create table a as (select * from t where i = ';')", 'a'),
    (' create table a as(select * from t)', 'a'),
    (' create table a as select * from t', 'a'),
])
def test_create_table_as_patched(query, table):
    """Tests patching an "create table as" statement from a query"""
    sql = pgmock.sql(query, pgmock.create_table_as(table).patch(rows=[(1,), (2,)],
                                                                cols=['a']))
    assert sql == 'create table a as SELECT * FROM (VALUES (1),(2)) AS pgmock("a")'


@pytest.mark.parametrize('query, selectors, expected', [
    (' insert into a select * from t; select * from b', [pgmock.insert_into('a').body()],
     'select * from t'),
    (' insert into a select * from t ', [pgmock.insert_into('a').body()],
     'select * from t '),
    (' insert into a(my, cols) select * from t ', [pgmock.insert_into('a'), pgmock.body()],
     ' select * from t '),
    (' insert into a(my, cols) (select * from t)  ; ', [pgmock.insert_into('a'), pgmock.body()],
     ' (select * from t)  '),
    (' create table a as (select * from t)', [pgmock.create_table_as('a'), pgmock.body()],
     ' (select * from t)'),
    (' create table a as select * from t;', [pgmock.create_table_as('a').body()],
     ' select * from t'),
    pytest.mark.xfail(
        (' insert into a values (1), (2);', [pgmock.statement(0).body()], None),
        raises=pgmock.exceptions.NoMatchError)
])
def test_body(query, selectors, expected):
    """Tests getting the patchable body from a selector"""
    sql = pgmock.sql(query, *selectors)
    assert sql == expected


def test_unpatchable():
    """Tests that an error is raised when something is not patchable"""
    with pytest.raises(pgmock.exceptions.UnpatchableError):
        pgmock.sql('create table t1', pgmock.statement(0).patch(rows=[], cols=['c1']))


def test_patch_alias_wo_columns():
    """Tests that an error is raised when trying to patch an expression that has an alias
       without providing columns"""
    with pytest.raises(pgmock.exceptions.ColumnsNeededForPatchError):
        pgmock.sql('select t1.c1 from t1', pgmock.table('t1').patch(rows=[('val',)]))


@pytest.mark.parametrize('func, args, kwargs, expected_chain', [
    (pgmock.statement, [0], {}, [('statement', (0,), {'end': None})]),
    (pgmock.insert_into, ['table'], {}, [('insert_into', ('table',), {})]),
    (pgmock.subquery, ['alias'], {}, [('subquery', ('alias',), {})]),
    (pgmock.table, ['table_name'], {}, [('table', ('table_name',), {'alias': None})]),
    (pgmock.mock, ['connectable'], {}, []),
    (pgmock.patch, [], {},
     [('patch', [], {'selector': None, 'rows': None, 'cols': None, 'side_effect': None})]),
])
def test_functional_interface(func, args, kwargs, expected_chain):
    """Verify the primary functional interface builds the appropriate render chain"""
    renderable = func(*args, **kwargs)
    assert renderable._chain == expected_chain


@pytest.mark.parametrize('query, table, alias', [
    ('select t1.c1 from t1', 't1', None),
    ('select a.c1 from t1 AS a', 't1', 'a'),
    ('select t1.c1 from t1; select t1.c1 from t1', 't1', None),
    pytest.mark.xfail(
        ('select a.c1 from t1 AS a', 't1', 'b'), raises=pgmock.exceptions.NoMatchError),
])
def test_mock_context_manager(transacted_postgresql_db, query, table, alias):
    """Tests patching using the context manager"""
    with pgmock.mock(transacted_postgresql_db.connection) as mock:
        mock.patch(pgmock.table(table, alias=alias),
                   [('val1.1',), ('val1.2',)],
                   ['c1'])

        res = transacted_postgresql_db.connection.execute(query)
        assert list(res) == [('val1.1',), ('val1.2',)]
        assert len(mock.renderings) == 1


@pytest.mark.parametrize('replace_new_patch_aliases', [
    None,  # Ensures that the default behavior is to replace new patch aliases
    True,
    pytest.mark.xfail(False, raises=sqla.exc.ProgrammingError)
])
def test_mock_context_manager_w_sqlalchemy_select(transacted_postgresql_db,
                                                  replace_new_patch_aliases):
    """Tests patching using the context manager with a SQLAlchemy select statement"""
    with pgmock.mock(transacted_postgresql_db.connection,
                     replace_new_patch_aliases=replace_new_patch_aliases) as mock:
        mock.patch(pgmock.table('schema.table_name'),
                   [('val1.1',), ('val1.2',)],
                   ['name'])

        table = sqla.Table('table_name', sqla.MetaData(), sqla.Column('name', sqla.String(50)),
                           schema='schema')
        query = sqla.select([table.c.name])

        res = transacted_postgresql_db.connection.execute(query)
        assert list(res) == [('val1.1',), ('val1.2',)]
        assert len(mock.renderings) == 1


def test_mock_context_manager_w_side_effects(transacted_postgresql_db):
    """Tests patching using the context manager and a side effect that ignores the first query"""
    with pgmock.mock(transacted_postgresql_db.connection) as mock:
        mock.patch(pgmock.table('t1', alias='a'),
                   side_effect=[None,
                                pgmock.data(rows=[('val1.1',), ('val1.2',)],
                                            cols=['c1'])])

        transacted_postgresql_db.connection.execute('SELECT * from pg_cursors;')
        res = transacted_postgresql_db.connection.execute('select a.c1 from t1 AS a')
        assert list(res) == [('val1.1',), ('val1.2',)]
        assert len(mock.renderings) == 2


def test_mock_context_manager_side_effect_exhausted(transacted_postgresql_db):
    """Tests patching using the context manager and exhausting a side effect"""
    with pgmock.mock(transacted_postgresql_db.connection) as mock:
        mock.patch(pgmock.table('t1', alias='a'), side_effect=[None])

        transacted_postgresql_db.connection.execute('SELECT * from pg_cursors;')

        with pytest.raises(pgmock.exceptions.SideEffectExhaustedError):
            transacted_postgresql_db.connection.execute('SELECT * from pg_cursors;')


def test_mock_context_manager_wo_connectable():
    """Tests trying to use a mock without a connectable"""
    with pytest.raises(pgmock.exceptions.NoConnectableError):
        with pgmock.mock(None):
            pass


def test_patched_types_serialized_properly(transacted_postgresql_db):
    """Ensures that different python types are serialized into VALUES properly"""
    rows = [
        (1, 1, "wes's string",
         dt.datetime(2012, 1, 2, 12), dt.datetime(2012, 1, 2, tzinfo=dt.timezone.utc),
         dt.time(12, 1, 1), dt.date(2012, 1, 2), {'json': 'field'}, True),
        (2, 2.5, "other string",
         dt.datetime(2012, 1, 2, 2), dt.datetime(2012, 1, 1, tzinfo=dt.timezone.utc),
         dt.time(12, 1, 2), dt.date(2012, 1, 3), {'json': 'field'}, False),
    ]
    cols = ['int', 'float', 'str', 'timestamp', 'timestamptz', 'time', 'date', 'json', 'bool']
    sql = pgmock.sql('select * from t1', pgmock.patch(pgmock.table('t1'), rows, cols))

    res = list(transacted_postgresql_db.connection.execute(sql))
    assert res == rows


@pytest.mark.parametrize('rows, columns, expected', [
    ([[None, 'string', '2017-01-02'], [1, None, None]],
     ['int::int', 'string', 'time::timestamp'],
     [(None, 'string', dt.datetime(2017, 1, 2)), (1, None, None)]),
    ([[dt.datetime(2017, 1, 2)]], ['time::timestamp'], [(dt.datetime(2017, 1, 2, 0, 0),)])
])
def test_table_patch_w_type_hints(rows, columns, expected, transacted_postgresql_db):
    """Tests patching tables when selecting"""
    patch = pgmock.patch(pgmock.table('t'), rows, columns)
    sql = pgmock.sql('select * from t', patch)

    res = transacted_postgresql_db.connection.execute(sql)
    assert list(res) == expected
