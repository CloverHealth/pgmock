"""
pgmock.render
-------------

Contains the primary functionality for rendering selected and patched SQL expressions
"""
import collections
import copy
import datetime as dt
import functools
import json
import re
import uuid

import sqlalchemy as sqla

import pgmock.config
import pgmock.exceptions


Rendering = collections.namedtuple('Rendering', ['original', 'rendered'])
RenderMethod = collections.namedtuple('RenderMethod', ['name', 'args', 'kwargs'])


def sql(query, *selectors, safe_mode=None):
    """Renders SQL from a query and selector.

    Args:
        query (str): The SQL query
        *selectors (Selector): The selector(s) of the query to render. If multiple
            selectors are provided as positional arguments, they are automatically
            chained together.
        safe_mode (bool, optional): If ``True``, used stripped SQL
            when using selectors. This has a performance hit but
            can result in more accurate searching. If ``None``,
            defaults to the globally configured value (which
            defaults to ``False``). More information on this
            can be viewed at `pgmock.config.set_safe_mode`.

    Returns:
        str: The rendered SQL

    Raises:
        Any exceptions that can be thrown by the selector during rendering

    Examples:
        Render the SQL from a subquery aliased with "a"

        .. code-block:: python

            subquery_sql = pgmock.sql(sql_string, pgmock.subquery('a'))


    """
    if safe_mode is None:
        safe_mode = pgmock.config.get_safe_mode()

    selector = chain(*selectors) if selectors else Renderable()
    with pgmock.config.set_safe_mode(safe_mode):
        return str(sqla.text(selector.render(query).sql_view))


def sql_file(file_name, *selectors, safe_mode=None):
    """Renders SQL from a sql file and selector.

    Args:
        file_name (str): The SQL file name
        *selectors (Selector): The selector(s) of the query to render. If multiple
            selectors are provided as positional arguments, they are automatically
            chained together.
        safe_mode (bool, optional): If ``True``, used stripped SQL
            when using selectors. This has a performance hit but
            can result in more accurate searching. If ``None``,
            defaults to the globally configured value (which
            defaults to ``False``). More information on this
            can be viewed at `pgmock.config.set_safe_mode`.

    Returns:
        str: The rendered SQL

    Raises:
        Any exceptions that can be thrown by the selector during rendering

    Examples:
        Render the SQL from a file that has a subquery aliased with "a"

        .. code-block:: python

            subquery_sql = pgmock.sql_file(sql_file_path, pgmock.subquery('a'))
    """
    with open(file_name) as sql_file:
        contents = sql_file.read()
        return sql(contents, *selectors, safe_mode=safe_mode)


def _find_enclosing_paren(sql, paren_idx, direction=1):
    """Finds the enclosing paren after a given direction

    If direction == 1, assumes a right paren is being found and starting
    from a left paren. If direction == -1, assumes a left paren is being
    found starting from a right paren

    Returns:
        int: The index of the matching paren

    Raises:
        `InvalidSQLError`: When a matching paren cannot be found
    """
    err_msg = (
        'Could not find enclosing parentheses on SQL starting at position'
        ' "{}" and going direction "{}". This happens when'
        ' left and right parens in the SQL do not match'
        ' (e.g. "WITH name AS (" has no matching right paren)'
    )

    parens_unmatched = 0
    paren_start = '(' if direction == 1 else ')'
    paren_end = ')' if direction == 1 else '('
    i = 0
    for char in sql[paren_idx + direction::direction]:
        if char == paren_start:
            parens_unmatched += 1
        elif char == paren_end:
            if parens_unmatched != 0:
                parens_unmatched -= 1
            else:
                break
        i += 1
    else:
        raise pgmock.exceptions.throw(pgmock.exceptions.InvalidSQLError,
                                      err_msg.format(paren_idx, direction),
                                      sql)

    return paren_idx + (i + 1) * direction


_SPLITTER_REGEXES = {
    None: re.compile(r'(--|[\'"]|/\*)'),
    '--': re.compile(r'(\n)'),
    "'": re.compile(r"(')"),
    '/*': re.compile(r'(\*/)'),
}


def _strip_comments_and_string_literals(sql):
    """Strip comments and string literals from SQL query"""
    stripped_sql = ''
    previous_split_token = None

    while sql:
        split_regex = _SPLITTER_REGEXES[previous_split_token]
        split_parts = split_regex.split(sql, 1)

        if len(split_parts) < 3:
            remaining_text = ''.join(split_parts)
            if previous_split_token:
                # Hit end of string before finding a closing match. This isn't
                # our problem, so we'll return what we currently have.
                return stripped_sql + ' ' * len(remaining_text)
            return stripped_sql + remaining_text

        prefix, this_split_token, rest = split_parts

        if previous_split_token is not None:
            # Inside a discard region, toss everything
            stripped_sql += (' ' * len(prefix)) + this_split_token
            previous_split_token = None
        else:
            # We're not inside a discard region, keep this text.
            stripped_sql += prefix + this_split_token
            previous_split_token = this_split_token

        sql = rest

    return stripped_sql


def _get_end_statement(sql, start):
    """Given a value and starting position, find the end of the statement

    This function assumes all comments and string literals have been stripped in the sql

    Returns:
        int: The index of the end of the statement
    """
    found = sql.find(';', start)
    return len(sql) if found == -1 else found


def _to_sql_value(val, col_type=None):
    """Serializes a value into a Postgres VALUE string"""
    PG_VALUE_SERIALIZERS = {
        bool: lambda v: 'TRUE' if v else 'FALSE',
        str: lambda v: "'%s'" % v.replace("'", "''"),
        int: str,
        float: str,
        dict: lambda v: "'%s'" % json.dumps(v).replace("'", "''"),
        dt.datetime: lambda v: "'%s'" % v.isoformat(),
        dt.date: lambda v: "'%s'" % v.isoformat(),
        dt.time: lambda v: "'%s'" % v.isoformat(),
        uuid.UUID: lambda v: "'%s'" % str(v),
    }
    PG_TYPES = {
        dict: lambda v: 'JSON',
        dt.datetime: lambda v: 'TIMESTAMP%s' % ('TZ' if v.tzinfo else ''),
        dt.date: lambda v: 'DATE',
        dt.time: lambda v: 'TIME%s' % ('TZ' if v.tzinfo else ''),
        uuid.UUID: lambda v: 'UUID'
    }
    if not col_type and val.__class__ in PG_TYPES:
        col_type = PG_TYPES[val.__class__](val)

    if val.__class__ in PG_VALUE_SERIALIZERS:
        serialized = PG_VALUE_SERIALIZERS[val.__class__](val)
    elif val is None:
        serialized = 'null'
    else:
        msg = 'value "{}" of type "{}" cannot be serialized'.format(val, type(val))
        pgmock.exceptions.throw(pgmock.exceptions.ValueSerializationError, msg)

    if col_type:
        serialized += '::%s' % col_type

    return serialized


def _row_to_sql_values(row, col_types):
    """Serializes an entire row to a Postgres VALUES list, filling in nulls for
       any columns that don't exist in the row"""
    if col_types and len(col_types) > len(row):
        row = list(row) + [None] * (len(col_types) - len(row))

    if col_types:
        serialized = (_to_sql_value(val, col_type) for val, col_type in zip(row, col_types))
    else:
        serialized = (_to_sql_value(val) for val in row)

    return '(' + ','.join(serialized) + ')'


def _convert_dict_rows_to_lists(dict_rows, cols):
    """
    Given a list of rows as dictionaries, convert it to a list of lists
    depending on the columns

    .. note::

        This function intentianally pre-allocates lists and does try/excepts
        around the full body for key errors in order to remain speedy and
        avoid unecessary branching / lookups.
    """
    col_pos = {col: i for i, col in enumerate(cols)}
    null_row = [None] * len(cols)
    list_rows = [null_row[:] for i in range(len(dict_rows))]

    row_num = 0
    try:
        for dict_row, list_row in zip(dict_rows, list_rows):
            for col, val in dict_row.items():
                list_row[col_pos[col]] = val
            row_num += 1
    except KeyError:
        pgmock.exceptions.throw(
            pgmock.exceptions.ColumnMismatchInPatchError,
            (
                'Row {} in patch data provided data for column "{}",'
                ' which is missing in the provided columns for the patch'
                ' (provided columns - "{}")'
            ).format(row_num, col, ', '.join(cols)))

    return list_rows


def _gen_values(rows, cols=None, alias=None, select_all_from=False):
    """Generates a Postgres VALUES list of a list of rows and columns.

    If columns aren't provided, assume the length of each row is equal to the first row

    If ``select_all_from`` is ``True``, returns a ``SELECT * FROM VALUES ...`` as
    the patch

    Note: This function does not assert that each row has the same number of columns
    """
    # Postgres VALUES lists cannot syntactically handle empty lists. Instead,
    # make an empty row and limit the results to 0
    empty_values = False if rows else True
    rows = [[]] if not rows else rows
    cols = cols or []
    col_types = [None if '::' not in col else col.split('::')[1] for col in cols]
    col_names = [col if '::' not in col else col.split('::')[0] for col in cols]

    if rows and isinstance(rows[0], dict):
        if not cols:
            pgmock.exceptions.throw(
                pgmock.exceptions.ColumnsNeededForPatchError,
                (
                    'Columns must also be provided when using list of dictionaries as rows'
                    ' to pgmock.patch or pgmock.data'
                ))
        rows = _convert_dict_rows_to_lists(rows, col_names)

    values = 'VALUES {}'.format(
        ','.join(_row_to_sql_values(row, col_types) for row in rows)
    )
    if empty_values:
        values += ' LIMIT 0'
    if alias:
        # escape all, in order to avoid hitting reserved keywords
        escaped_col_names = ['"%s"' % (col) for col in col_names]
        values = '(%s) AS %s(%s)' % (values, alias, ','.join(escaped_col_names))
    if select_all_from:
        values = 'SELECT * FROM %s' % values

    return values


class PatchParams:
    """Parameters for controlling patch behavior"""
    def __init__(self, patch_alias=None, select_all_from=False, orig_alias=None):
        #: If set, will be used as the alias for the patch
        #: (e.g. ``(VALUES ...) as patch_alias(...)``)
        self.patch_alias = patch_alias

        #: If ``True``, will put a ``SELECT * FROM`` in front of the patch
        self.select_all_from = select_all_from

        #: If the original alias of what is being patched differs from the alias
        #: for the patch, all references to the original alias will also be updated
        #: to the patch alias.
        #: For example, say we are patching ``SELECT schema.table_name.c FROM schema.table_name``.
        #: ``schema.table_name`` is not a valid patch alias, so we use ``table_name`` as the
        #: patch name. This will in turn update the SQL to be
        #: ``SELECT        table_name.c FROM (VALUES ...) AS table_name(...)`` (the original
        #: spacing of the SQL is preserved for internal implementation reasons)
        self.orig_alias = orig_alias or patch_alias


class View:
    """Models a view into an SQL blob

    A view can consist of two different slices into SQL:

    1. ``bounds`` - The primary view into the SQL. Typically encapsulates whatever a selector
       selects. For example, the bounds of an ``insert_into`` selector will encapsulate the
       entire "insert into" statement.
    2. ``patch`` - The part of the SQL that can be patched (if applicable). For example, if
       an "insert into" statement has a "select", the ``patch`` slice will contain the entire
       select expression.
    3. ``patch_params`` - If the SQL can be patched, the parameters that define how the patch
       should take place
    """
    def __init__(self, bounds, patch=None, patch_params=None):
        self.bounds = slice(bounds.start, bounds.stop)
        self.patch = slice(patch.start, patch.stop) if patch else None
        self.patch_params = patch_params or PatchParams()

    def from_offset(self, offset):
        """Return a view relative to an offset"""
        return View(
            bounds=slice(self.bounds.start + offset,
                         self.bounds.stop + offset),
            patch=slice(self.patch.start + offset,
                        self.patch.stop + offset) if self.patch else None,
            patch_params=self.patch_params)

    def check_is_patchable(self, cols):
        """Checks that a rendered view can be patched.

        Raises the appropriate error message if a view cannot be patched
        """
        if not self.patch:
            msg = 'Expression is not able to be patched.'
            pgmock.exceptions.throw(pgmock.exceptions.UnpatchableError, msg)

        if self.patch_params.patch_alias and not cols:
            msg = 'Must provide columns when patching SQL with aliases.'
            pgmock.exceptions.throw(pgmock.exceptions.ColumnsNeededForPatchError,
                                    msg)


def chain(*renderables):
    """Chains renderable objects

    pgmock allows renderable objects (selectors and patches) to
    be chained to one another like so::

        pgmock.statement(0).table('table').patch(...)

    Sometimes this syntax is undesirable, especially when working
    with multiple patches. This function essentially implements that
    syntax. For example, calling::

        pgmock.patch('patch1').patch('patch2')

    is equivalent to calling::

        chain(pgmock.patch('patch1'), pgmock.patch('patch2'))

    Raises:
        `TypeError`: When no renderables are supplied
        `SelectorChainingError`: When the selectors are not compatible for
        chaining
    """
    if not renderables:  # pragma: no cover
        raise TypeError('At least one renderable must be given to chain()')

    chained = copy.deepcopy(renderables[0])
    for renderable in renderables[1:]:
        chained.chain(renderable)

    return chained


class Renderable:
    """Base class for renderable selectors

    Child classes implement renderable methods by exposing methods with the
    Renderable.chainable_render_method decorator. These methods are
    appended to a chain of rendering methods that are later called when
    ``render`` is called.
    """
    def __init__(self, renderable=None):
        if renderable and not isinstance(renderable, Renderable):  # pragma: no cover
            raise TypeError('Must provide a selector to pgmock Renderables')

        # The chain of renderable methods
        self._chain = [] if not renderable else renderable._chain
        # The renderings
        self.renderings = [] if not renderable else renderable.renderings

    def chain(self, renderable):
        """Chains another renderable to this one

        Raises:
            `SelectorChainingError`: When the selectors are not compatible for
            chaining
        """
        if not isinstance(renderable, type(self)):
            pgmock.exceptions.throw(
                pgmock.exceptions.SelectorChainingError,
                '"{}" cannot be chained with "{}"; types are incompatible'.format(self, renderable)
            )
        self._chain.extend(renderable._chain)

    @staticmethod
    def chainable_render_method(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            render_method = func(*args, **kwargs)
            self = args[0]
            if not render_method:
                self._chain.append(RenderMethod(name=func.__name__, args=args[1:], kwargs=kwargs))
            else:
                assert isinstance(render_method, RenderMethod)
                self._chain.append(render_method)
            return self
        return wrapper

    def __str__(self):
        """Returns a human-readable version of the chain.

        Assumes the chain was constructed using pgmock's top-level interface
        """
        if not self._chain:
            str_chain = 'pgmock.render.Renderable()'
        else:
            str_chain = 'pgmock'
            for render_method in self._chain:
                args = [repr(a) for a in render_method.args]
                args.extend([
                    '{}={}'.format(k, repr(v))
                    for k, v in render_method.kwargs.items()
                ])
                str_chain += '.{}({})'.format(render_method.name, ', '.join(args))
        return str_chain

    def render(self, sql):
        """Renders SQL with the rendering chain and maintains a list of renderings"""
        renderer = pgmock.render.Renderer(sql)

        for render_method in self._chain:
            renderer = getattr(renderer, render_method.name)(*render_method.args,
                                                             **render_method.kwargs)

        # If there are multiple render views, SQL isn't able to be rendered
        rendered = renderer.sql_view if len(renderer.views) == 1 else None
        self.renderings.append(Rendering(original=sql, rendered=rendered))
        return renderer


class RenderSQL:
    """An object that maintains SQL for rendering depending on if safe mode is turned on"""
    def __init__(self, sql):
        self.stripped_sql = None
        if pgmock.config.get_safe_mode():
            self.stripped_sql = _strip_comments_and_string_literals(sql)
            assert len(self.stripped_sql) == len(sql)
        self.raw_sql = sql
        self.search_sql = self.stripped_sql or self.raw_sql


class Renderer:
    """Maintains a view into a SQL blob and renders patches or expressions.

    When a ``Renderer`` is instantiated with SQL, it initially has a view that
    represents the entire SQL blob. When calling any chainable rendering method
    (e.g. ``select``, ``insert_into``, etc), the renderer adjusts its view to
    match the appropriate rendering location. The underlying SQL remains the same
    unless calling the ``patch`` method, which will replace the patchable area
    with a VALUES expression.

    The view into the SQL of the renderer can be accessed with the ``view``
    property.
    """
    def __init__(self, sql, view=None):
        assert isinstance(sql, (str, RenderSQL))
        #: Contains the SQL used for rendering. When loaded in safe mode,
        #: stripped SQL will be searched instead of raw SQL
        self.rendering_sql = RenderSQL(sql) if isinstance(sql, str) else sql

        #: The view into the raw SQL. Refined when rendering selections
        if view is None:
            views = [View(slice(0, len(self.rendering_sql.raw_sql)))]
        elif not isinstance(view, (list, tuple)):
            views = [view]
        else:
            views = view

        self.views = views

        # If any views are nested, it results in ambiguity for rendering and patching
        for i, right_view in enumerate(self.views[1:], 1):
            if right_view.bounds.start < self.views[i - 1].bounds.stop:
                pgmock.exceptions.throw(  # pragma: no branch
                    pgmock.exceptions.NestedMatchError,
                    'Nested matches were found in your selection.',
                    [self.raw_sql[view.bounds] for view in self.views]
                )

    @property
    def view(self):
        if len(self.views) != 1:
            msg = (
                'An invalid operation has occurred on a selector that has multiple matches,'
                ' for example selecting the body of two "insert into" statements.'
                ' Refine your selection by using the array syntax on your selector.'
            )
            pgmock.exceptions.throw(  # pragma: no branch
                pgmock.exceptions.MultipleMatchError,
                msg,
                [self.raw_sql[view.bounds] for view in self.views]
            )

        return self.views[0]

    @property
    def sql_view(self):
        return self.raw_sql[self.view.bounds]

    @property
    def search_view(self):
        """Returns what SQL should be used when doing regex searching"""
        return self.rendering_sql.search_sql[self.view.bounds]

    @property
    def raw_sql(self):
        """Returns the original raw SQL passed into the renderer"""
        return self.rendering_sql.raw_sql

    def __getitem__(self, index):
        """Filter views of a renderer"""
        return Renderer(self.rendering_sql, self.views[index])

    def body(self):  # pylint: disable=inconsistent-return-statements
        """Render the patchable body of a selector"""
        if self.view.patch:
            return Renderer(self.rendering_sql, View(self.view.patch, patch=self.view.patch))
        else:
            pgmock.exceptions.throw(pgmock.exceptions.NoMatchError, 'No patchable body found.',
                                    self.sql_view)

    def statement(self, start, end=None):
        """Renders the statement(s) from the start index to the end (exclusive)

        Note: This naively splits the SQL by the semicolon and does not handle the case of it
        existing in the comments or some other string literal
        """
        sql = self.search_view
        parts = sql.split(';')
        end = end or start + 1
        assert end >= start
        assert start >= 0

        if start >= len(parts) or end > len(parts):
            msg = 'Found {} statements. Range of [{}:{}] is out of bounds.'.format(len(parts),
                                                                                   start,
                                                                                   end)
            pgmock.exceptions.throw(pgmock.exceptions.StatementParseError, msg, sql)

        stmt_start = sum(len(part) for part in parts[:start]) + start
        stmt_end = stmt_start + sum(len(part) for part in parts[start:end]) + (end - start - 1)

        view = View(slice(stmt_start, stmt_end)).from_offset(self.view.bounds.start)
        return Renderer(self.rendering_sql, view)

    def subquery(self, alias):
        """Renders a subquery with an alias

        Searches for a right paren and alias and then obtain the matching left paren with
        a pre-built index
        """
        sql = self.search_view
        no_match_msg = 'No subquery found for alias "{}".'.format(alias)

        matches = list(re.finditer(r'\)\s*(as\s+)?%s(?!\w)' % re.escape(alias), sql,
                                   flags=re.IGNORECASE))
        if not matches:
            pgmock.exceptions.throw(pgmock.exceptions.NoMatchError, no_match_msg, sql)

        views = []
        for match in matches:
            right_paren, alias_end = match.span()
            left_paren = _find_enclosing_paren(sql, right_paren, -1)

            select_bounds = slice(left_paren + 1, right_paren)
            patch_bounds = slice(left_paren, alias_end)
            patch_params = PatchParams(patch_alias=alias)
            view = View(select_bounds,
                        patch=patch_bounds,
                        patch_params=patch_params).from_offset(self.view.bounds.start)
            views.append(view)

        return Renderer(self.rendering_sql, views)

    def cte(self, alias):
        """Renders a CTE with an alias

        Searches for a CTE alias after a WITH or after a comma followed by a left paren. Finds the
        other right paren with the pre-built index
        """
        sql = self.search_view
        no_match_msg = 'No CTE found for alias "{}".'.format(alias)

        matches = list(re.finditer(
            r'(?:with\s+|,\s*)%s(?:\s*\(.*\)\s*|\s+)as\s*\(' % re.escape(alias), sql,
            flags=re.IGNORECASE))
        if not matches:
            pgmock.exceptions.throw(pgmock.exceptions.NoMatchError, no_match_msg, sql)

        views = []
        for match in matches:
            left_paren = match.span()[1] - 1
            right_paren = _find_enclosing_paren(sql, left_paren)

            cte_bounds = slice(left_paren + 1, right_paren)
            patch_params = PatchParams(patch_alias='pgmock', select_all_from=True)
            view = View(cte_bounds,
                        patch=cte_bounds,
                        patch_params=patch_params).from_offset(self.view.bounds.start)
            views.append(view)

        return Renderer(self.rendering_sql, views)

    def insert_into(self, table):
        """Renders an "insert into" statement

        Searches for an "insert into" statement with a select and returns a new renderer
        with the proper view.

        This does not handle the case when the "insert into" statement does not have a select
        and a `NoMatchError` is thrown instead.
        """
        sql = self.search_view
        matches = list(re.finditer(r'insert\s+into\s+%s(?:\s*\(|\s+[\w/-])' % re.escape(table),
                                   sql,
                                   flags=re.IGNORECASE))
        if not matches:
            pgmock.exceptions.throw(pgmock.exceptions.NoMatchError,
                                    'No "insert into" statement found.',
                                    sql)

        views = []
        for match in matches:
            insert_start, insert_end = match.span()
            insert_end -= 1
            end_idx = _get_end_statement(sql, insert_end)
            if sql[insert_end] == '(':
                right_paren = _find_enclosing_paren(sql, insert_end) + 1

                # If the space between the end idx and insert end is
                # whitespace, it means this is a insert into (statement)
                # rather than an insert into (table_def) statement
                if sql[right_paren:end_idx].strip():
                    insert_end = right_paren

            patch_bounds = slice(insert_end, end_idx)
            view = View(slice(insert_start, end_idx),
                        patch=patch_bounds).from_offset(self.view.bounds.start)
            views.append(view)

        return Renderer(self.rendering_sql, views)

    def create_table_as(self, table):
        """Renders a "create table as" statement

        Searches for "create table {table_name}(...) as"
        """
        sql = self.search_view
        matches = list(re.finditer(r'create\s+table\s+%s(?:\s*\(.*\)\s*|\s+)as' % re.escape(table),
                                   sql,
                                   flags=re.IGNORECASE))
        if not matches:
            pgmock.exceptions.throw(pgmock.exceptions.NoMatchError,
                                    'No "create table as" statement found.',
                                    sql)

        views = []
        for match in matches:
            create_start, cta_end = match.span()
            end_idx = _get_end_statement(sql, create_start)

            patch_bounds = slice(cta_end, end_idx)
            patch_params = PatchParams(patch_alias='pgmock', select_all_from=True)
            view = View(slice(create_start, end_idx),
                        patch=patch_bounds,
                        patch_params=patch_params).from_offset(self.view.bounds.start)
            views.append(view)

        # When patching a "create_table_as", be sure to patch it with a
        # SELECT * FROM VALUES AS pgmock() in order for columns to be preserved when patching
        return Renderer(self.rendering_sql, views)

    def table(self, table, alias=None):
        """Renders a "table" of an SQL blob that can have an alias

        An view is built around the table and (optionally) its alias so that it can
        be patched or rendered.
        """
        sql = self.search_view
        if alias:
            regex = r'(?P<pre>(from|join)\s+)%s\s+(as\s+)?%s(?!\w)' % (re.escape(table),
                                                                       re.escape(alias))
        else:
            regex = r'(?P<pre>(from|join)\s+)%s(?!\w)' % re.escape(table)

        matches = list(re.finditer(regex, sql, flags=re.IGNORECASE))
        if not matches:
            msg = 'No table "{}" {}found.'.format(
                table,
                'with alias "{}" '.format(alias) if alias else '')
            pgmock.exceptions.throw(pgmock.exceptions.NoMatchError, msg, sql)

        views = []
        for match in matches:
            bounds = slice(match.span()[0] + len(match.group('pre')), match.span()[1])

            patch_alias = alias
            if not patch_alias:
                # Postgres aliases cannot have a '.' in them, so use the table name without the
                # schema as the patch alias name
                patch_alias = table if '.' not in table else table.split('.')[1]

            patch_params = PatchParams(patch_alias=patch_alias, orig_alias=alias or table)
            views.append(View(bounds, patch=bounds, patch_params=patch_params))

        return Renderer(sql, views)

    def patch(self, selector=None, rows=None, cols=None, side_effect=None):
        """Patches an SQL expression

        If ``selector`` is ``None``, tries to patch the current renderable SQL. Otherwise
        tries to apply ``selector`` to the SQL and patch that portion of it.

        Proceeds in the following steps:

        1. Renders the ``selector`` inside of the current SQL view if provided
        2. Generates a VALUES list if the SQL expression can be patched
        3. Replaces the patchable area with the VALUES blob. Adjusts the view of the
           modified SQL accordingly

        Args:
            selector (Selector, optional): A selector to further target a patchable SQL
                expression
            rows (List[tuple], default=[]): A list of rows to patch.
            cols (List[str], optional): A list of columns. Required if patching an expression
                that has a name or alias (e.g a table or subquery). If more columns are provided
                than values in the row, other values are filled with ``null``.
            side_effect (List[(rows, cols)]): A list of return values, used when patching return
                values for each subsequent rendering. If ``None`` is provided for any values,
                patching is ignored.

        Raises:
            `UnpatchableError`: When the expression cannot be patched
            `ColumnsNeededForPatchError`: When patching an expression with an alias and not
                providing columns
        """
        # pylint: disable=too-many-locals
        rows = rows or []
        if side_effect:
            if rows or cols:  # pragma: no cover
                raise ValueError('"rows" and "cols" cannot be used with "side_effect" is defined')
            next_side_effect = side_effect()
            if next_side_effect is None:
                # Skip the patch is the side effect is None
                return self
            else:
                rows, cols = next_side_effect

        rendered = selector.render(self.sql_view) if selector else self

        adjustment = 0
        patched_sql = self.raw_sql

        for rendered_view in rendered.views:
            patch_args = rendered_view.patch_params
            rendered_view.check_is_patchable(cols)

            values = _gen_values(rows, cols, patch_args.patch_alias, patch_args.select_all_from)

            patch = rendered_view.patch
            if selector:
                patch = slice(self.view.bounds.start + rendered_view.patch.start,
                              self.view.bounds.start + rendered_view.patch.stop)

            # Create new SQL and then adjust the view based on how much of the SQL was replaced
            # Intentionally add space before the patch. This helps avoid any syntactical errors
            # that can happen when VALUES appears immediately after a keyword
            patched_sql = '{} {}{}'.format(patched_sql[:patch.start - adjustment],
                                           values,
                                           patched_sql[patch.stop - adjustment:])

            # If the original alias of the patch is set and doesn't match the patch alias, all
            # references to the original reference need to be updated
            if pgmock.config.get_replace_new_patch_aliases():
                if patch_args.patch_alias and patch_args.orig_alias != patch_args.patch_alias:
                    assert len(patch_args.orig_alias) >= len(patch_args.patch_alias)
                    replace_alias = patch_args.patch_alias.rjust(len(patch_args.orig_alias)) + '.'
                    search = r'\b%s\.' % re.escape(patch_args.orig_alias)
                    patched_sql = re.sub(search, replace_alias, patched_sql)

            adjustment += (patch.stop - patch.start - (len(values) + 1))

        return Renderer(patched_sql, View(slice(self.view.bounds.start,
                                                self.view.bounds.stop - adjustment)))
