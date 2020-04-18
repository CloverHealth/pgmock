"""Unit tests for the pgmock.render module"""
import uuid
import datetime as dt

import pytest
import pytest_pgsql

import pgmock.exceptions
import pgmock.render

TEST_UUID_STR = '754b2b75-96fb-4fcd-b719-adfe7ab45f11'


@pytest.mark.parametrize('rows, expected', [
    ([(1, '1', 1.1)], "VALUES (1,'1',1.1)"),
    ([(dt.datetime(2017, 6, 1, 12),)], "VALUES ('2017-06-01T12:00:00'::TIMESTAMP)"),
    ([(dt.datetime(2017, 6, 1, 12, tzinfo=dt.timezone.utc),)],
     "VALUES ('2017-06-01T12:00:00+00:00'::TIMESTAMPTZ)"),
    ([(dt.date(2017, 6, 1),)], "VALUES ('2017-06-01'::DATE)"),
    ([(dt.time(12, 1, 2),)], "VALUES ('12:01:02'::TIME)"),
    ([(dt.time(12, 1, 2, tzinfo=dt.timezone.utc),)], "VALUES ('12:01:02+00:00'::TIMETZ)"),
    ([(None,)], "VALUES (null)"),
    ([(True, False)], "VALUES (TRUE,FALSE)"),
    ([({'my': 'json'},)], "VALUES ('{\"my\": \"json\"}'::JSON)"),
    ([({"my": "quo'te"},)], "VALUES ('{\"my\": \"quo''te\"}'::JSON)"),
    ([(uuid.UUID(TEST_UUID_STR),)], "VALUES ('{}'::UUID)".format(TEST_UUID_STR)),
    pytest.mark.xfail(([(object(),)], None), raises=pgmock.exceptions.ValueSerializationError)
])
def test_gen_values_list(rows, expected):
    """Tests generating a VALUES list with pgmock.render._gen_values"""
    expression = pgmock.render._gen_values(rows)
    assert expression == expected


@pytest_pgsql.freeze_time('2015-1-1')
def test_gen_values_list_w_freeze_time(transacted_postgresql_db):
    """Tests generating a VALUES list with pgmock.render._gen_values when time is frozen

    We test for this case because the freezegun module patches the datetime object, previously
    causing serialization to break
    """
    expression = pgmock.render._gen_values([(dt.datetime.utcnow(),)])
    assert expression == "VALUES ('2015-01-01T00:00:00'::TIMESTAMP)"


def test_gen_values_alias_w_null():
    """Tests pgmock.render._gen_values with filling in nulls for missing columns"""
    rows = [(1, '1', 1.1), (2, '2', 2.2)]
    cols = ['a', 'b', 'c', 'fill']
    expression = pgmock.render._gen_values(rows, cols, 'd')
    assert (
        expression == "(VALUES (1,'1',1.1,null),(2,'2',2.2,null)) AS d(\"a\",\"b\",\"c\",\"fill\")"
    )


@pytest.mark.parametrize('rows, cols, expected', [
    pytest.mark.xfail(
        ([{'c1': 1, 'c2': '1', 'c3': 1.1}], [], None),
        raises=pgmock.exceptions.ColumnsNeededForPatchError
    ),
    pytest.mark.xfail(
        ([{'c1': 1, 'c2': '1', 'c3': 1.1}], ['d1', 'd2'], None),
        raises=pgmock.exceptions.ColumnMismatchInPatchError
    ),
    ([{'c1': 1, 'c2': '1', 'c3': 1.1}], ['c1', 'c2', 'c3'], "VALUES (1,'1',1.1)"),
    ([{'c1': 1}, {'c2': '1'}], ['c1', 'c2', 'c3'], "VALUES (1,null,null),(null,'1',null)"),
])
def test_gen_values_dict_rows(rows, cols, expected):
    """Tests pgmock.render._gen_values using dictionaries as rows"""
    expression = pgmock.render._gen_values(rows, cols)
    assert expression == expected


@pytest.mark.parametrize('sql, paren_idx, direction, expected_idx', [
    ('(())', 0, 1, 3),
    ('(())', 1, 1, 2),
    ('(())', 3, -1, 0),
    ('(())', 2, -1, 1),
    ('( stuff ( in between ))', 9, 1, 21),
    pytest.mark.xfail(('( ( )', 0, 1, None), raises=pgmock.exceptions.InvalidSQLError)
])
def test_find_enclosing_paren(sql, paren_idx, direction, expected_idx):
    idx = pgmock.render._find_enclosing_paren(sql, paren_idx, direction)
    assert idx == expected_idx


@pytest.mark.parametrize('sql, expected', [
    (
        "/*\na\nb\n*/\nselect * from table",
        "/*     */\nselect * from table"
    ),
    (
        "select * from table -- This is an in-line comment",
        "select * from table --                           "
    ),
    (
        "select * from table where mytext = '--' and mytext2 = 'a'",
        "select * from table where mytext = '  ' and mytext2 = ' '"
    ),
    (
        "select * from table where mytext = '--' -- This is an in-line comment",
        "select * from table where mytext = '  ' --                           "
    ),
    (
        "select * from table\n /*This is an in-line block comment*/ where mytext = '--'",
        "select * from table\n /*                                */ where mytext = '  '"
    ),
    (
        "select * from table\n /*This is an in-line /* block comment*/ where mytext = '--'",
        "select * from table\n /*                                   */ where mytext = '  '"
    ),
    (
        "select * from table\n /*This is an in-line /* block comment*/ --",
        "select * from table\n /*                                   */ --"
    ),
    (
        "/* -- ' \n*/-- strip this\n--comment\nselect * from table where i = 'vincent''s'",
        "/*       */--           \n--       \nselect * from table where i = '       '' '"
    ),
])
def test_strip_comments_and_string_literals(sql, expected):
    """Testing stripping comments from SQL statement

    Trailing newline differences are OK because behavior is the same in SQL.
    """
    expression = pgmock.render._strip_comments_and_string_literals(sql)
    assert expression == expected


@pytest.mark.parametrize('renderable, expected_repr', [
    (pgmock.statement(0).table('name'), "pgmock.statement(0, end=None).table('name')"),
    (pgmock.statement(0).table("name's"), 'pgmock.statement(0, end=None).table("name\'s")'),
    (pgmock.render.Renderable(), "pgmock.render.Renderable()")
])
def test_renderable_str(renderable, expected_repr):
    """Tests Renderable.__str___"""
    assert str(renderable) == expected_repr
