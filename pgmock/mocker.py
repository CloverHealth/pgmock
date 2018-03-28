"""
pgmock.mocker
---------------

Contains the primary functionality for patching and mocking SQLAlchemy queries
"""
import collections

import sqlalchemy.event as sqla_event
import sqlalchemy.orm.session as sqla_session

import pgmock.exceptions
import pgmock.render


Data = collections.namedtuple('Data', ['rows', 'cols'])


def data(rows=None, cols=None):
    """Creates patch data for a side effect.

    Args:
        rows (List[tuple], optional): A list of tuples of values to patch for each
            row. Each row must have the same length. If ``None``, defaults to an
            empty list.
        cols (List[str]): A list of columns.

    Returns:
        Data: A data object that can be used as input to a side effect of a patch,
        for example ``pgmock.patch(side_effect=[pgmock.data(rows=..., cols=...)])``
    """
    return Data(rows=rows, cols=cols)


def mock(connectable, replace_new_patch_aliases=None):
    """Creates a mock selector that can be patched.

    This is intended to be used as a context manager with a given SQLAlchemy
    connectable (e.g. an engine, session, connection, etc). For example::

        with pgmock.mock(engine) as mocker:
            mocker.patch(pgmock.table('my_table'), rows, cols)
            mocker.patch(pgmock.table('other_table'), rows, cols)

            # Run SQLAlchemy queries...

            # Assert the mocker was rendered with as many queries executed
            assert len(mocker.renderings) == num_expected_queries

    Any queries executed inside of the context manager will be patched by
    SQLAlchemy's ``before_cursor_execute`` event. Renderings of patched
    SQL can be obtained by examining the ``renderings`` property of the
    object, which is a list of tuples of the original and modified SQL
    of every query.

    If any of the patches cannot be matched during query execution, the relevant
    exceptions are raised. Specific patches can be applied to specific queries
    by using the ``side_effect`` argument of `pgmock.patch`.

    Args:
        connectable (SQLAlchemy connectable object): The connectable SQLAlchemy
            object (e.g engine, session, connection, etc)
        replace_new_patch_aliases (bool, optional): If ``True``,
            will replace any references to patch aliases when they differ from
            the original alias. If ``None``, uses the globally-configured
            value that defaults to ``True``. More information on this can
            be found at `pgmock.config.set_replace_new_patch_aliases`

    Returns:
        Mock: A chainable mock object that can be patched.

    Raises:
        Any error that can happen during rendering.
    """
    return Mocker(connectable=connectable, replace_new_patch_aliases=replace_new_patch_aliases)


def patch(selector=None, rows=None, cols=None, side_effect=None):
    """Applies a patch to a selector.

    Args:
        selector (Selector, optional). A selector to patch inside of the
            relevant SQL.
        rows (List[tuple], optional): A list of tuples of values to patch for each
            row. Each row must have the same length. If ``None``, patching is ignored.
        cols (List[str]): A list of columns. If more columns are provided than the
            length of the rows, ``null`` values are filled in for the missing values.
        side_effect(List[pgmock.data]): A list of side effects. Side effects can only
            be provided when ``rows`` and ``cols`` are not provided. Each side effect
            is rendered on each subsequent rendering of the patch. Side effects must
            be instantiated with ``pgmock.data`` and the arguments are ``rows``
            and ``cols``. Note: providing ``None`` as a side effect will ignore the
            patch for the rendering.

    Returns:
        Mock: A chainable mock object that can be patched.

    Raises:
        `UnpatchableError`: When the selector cannot be patched

    Examples:
        Patch a table "schema.table_name" with values

        .. code-block:: python

            patch = pgmock.patch(pgmock.table('schema.table_name'),
                                 rows=[(1, 2), (3, 4)],
                                 cols=['a', 'b'])
            patched_query = pgmock.sql(sql_string, patch)

        Patch a table "schema.table_name" with a side effect while
        using SQLAlchemy

        .. code-block:: python

            with pgmock.mock(connetion) as mocker:
                mocker.patch(pgmock.table('schema.table_name'),
                             side_effect=[
                                 None,
                                 pgmock.data([(1, 2), (3, 4)], ['a', 'b'])
                             ])
                # Do no patching on the first execution of the SQLAlchemy
                # connection since the side effect returns ``None`` the
                # first time
                connection.execute(...)
                # Now apply the patch the second time
                connection.execute(...)
    """
    return Mocker().patch(selector=selector, rows=rows, cols=cols, side_effect=side_effect)


class SideEffect:
    """A side effect for a mock

    Similar to traditional mock side effects, ``pgmock`` side effects are callables
    that return different results for each call. Currently ``pgmock`` only supports
    taking an iterable as a side effect's input. Taking another callable is intended
    to be supported in future versions
    """
    def __init__(self, side_effect):
        """Initializes the side effect and ensures its the proper type"""
        #: The index into the side effect
        self.iterable_idx = 0
        self.side_effect = side_effect

        if not isinstance(side_effect, (list, tuple)):
            raise TypeError('Side effects must be iterable')

        for se in self.side_effect:
            if not isinstance(se, Data) and se is not None:
                # While users could technically pass tuples, it's easy to get the ordering mixed up
                # with rows and cols
                raise TypeError('Side effect values must be instantiated with pgmock.data(...)')

    def __call__(self):
        if self.iterable_idx >= len(self.side_effect):
            # Raise custom error message
            pgmock.exceptions.throw(pgmock.exceptions.SideEffectExhaustedError,
                                    'Side effect of length {} has been exhausted'.format(
                                        len(self.side_effect)))

        self.iterable_idx += 1
        return self.side_effect[self.iterable_idx - 1]


class Mocker(pgmock.render.Renderable):
    """A renderable for patching expressions and tables

    When used as a context manager, the user must supply a SQLAlchemy connectable
    object (eg. Engine, Session, Connection, etc) to the constructor::

        with Mock(connectable=connectable) as mocker:
            ...

    When used as a context manager, the ``before_cursor_execute`` event is tracked
    and queries are patched when issued.
    """
    def __init__(self, renderable=None, connectable=None, replace_new_patch_aliases=None):
        super().__init__(renderable=renderable)
        if replace_new_patch_aliases is None:
            replace_new_patch_aliases = pgmock.config.get_replace_new_patch_aliases()
        self.replace_new_patch_aliases = replace_new_patch_aliases
        self._replace_new_patch_aliases_config = None

        self._query_hook = None

        # If the caller gives us a session, take the underlying connection or
        # engine instead.
        if isinstance(connectable, sqla_session.Session):  # pragma: no cover
            if connectable.bind is None:
                raise TypeError("Can't use unbound `Session` object for mocking.")
            connectable = connectable.bind

        self._connectable = connectable

    @pgmock.render.Renderable.chainable_render_method
    def patch(self, selector=None, rows=None, cols=None, side_effect=None):
        """Returns a chainable render method and ensures a side effect object is
           passed to the renderer"""
        # pylint: disable=no-self-use
        if selector and not isinstance(selector, pgmock.render.Renderable):  # pragma: no cover
            raise TypeError(
                'Must provide a selector to patch. Type provided = "{}"'.format(type(selector)))

        if side_effect and not isinstance(side_effect, SideEffect):
            side_effect = SideEffect(side_effect)

        return pgmock.render.RenderMethod(name='patch',
                                          args=[],
                                          kwargs={
                                              'selector': selector,
                                              'rows': rows,
                                              'cols': cols,
                                              'side_effect': side_effect
                                          })

    def start(self):
        """Starts the ``before_cursor_execute`` event listener"""
        if not self._connectable:
            raise pgmock.exceptions.throw(pgmock.exceptions.NoConnectableError,
                                          'Must provide a connectable when using context manager')
        self.stop()

        # pylint: disable=unused-argument
        @sqla_event.listens_for(self._connectable, 'before_cursor_execute', retval=True)
        def _hook(conn, cursor, statement, parameters, context, executemany):
            """Query hook to apply patches"""
            statement = self.render(statement).sql_view

            return statement, parameters

        # Set up our query modifier to listen for execution events
        self._query_hook = _hook
        sqla_event.listen(self._connectable, 'before_cursor_execute', _hook)

        # Set the configuration for replacing new patch aliases
        self._replace_new_patch_aliases_config = pgmock.config.set_replace_new_patch_aliases(
            self.replace_new_patch_aliases)
        self._replace_new_patch_aliases_config.__enter__()
        return self

    def stop(self):
        """Stops the ``before_cursor_execute`` event listener"""
        if self._query_hook:
            sqla_event.remove(self._connectable, 'before_cursor_execute', self._query_hook)
            self._query_hook = None
        if self._replace_new_patch_aliases_config:
            self._replace_new_patch_aliases_config.__exit__(None, None, None)
            self._replace_new_patch_aliases_config = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *error_args):
        self.stop()
