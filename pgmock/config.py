"""
pgmock.config
-------------

Configuration functions for ``pgmock``
"""

# Sentinel value, guaranteed to be unique
UNDEFINED_VALUE = object()


class _ContextableConfigValue:
    """
    Allows setting configuration variables that can be used
    as context managers

    Examples:

        Make a setter for a configuration variable:

        .. code-block:: python

            set_value = _ContextableConfigurationValue('default')

        Set the value globally:

        .. code-block:: python

            set_value('other_value')

        Set the value within a context manager:

        .. code-block:: python

            with set_value('yet_another_value'):
                ...

        A getter for the configuration variable can be made like:

        .. code-block:: python

            get_value = lambda: set_value.value
    """
    def __init__(self, initial_value):
        self.value = initial_value
        self._value_stack = []
        self._old_value = UNDEFINED_VALUE

    def __call__(self, new_value):
        self._old_value = self.value
        self.value = new_value
        return self

    def __enter__(self):
        if self._old_value is UNDEFINED_VALUE:
            raise TypeError('value cannot be directly used as a context manager')
        self._value_stack.append(self._old_value)
        self._old_value = UNDEFINED_VALUE
        return self

    def __exit__(self, *args):
        self.value = self._value_stack.pop()


set_safe_mode = _ContextableConfigValue(False)
"""Sets whether safe mode is turned on or off in ``pgmock``.

If ``safe_mode`` is ``True``, all selectors will be applied
to a stripped version of SQL that excludes comments and
string literals. This improves the accuracy of ``pgmock``
matching but comes with a performance hit.

Safe mode is set to ``False`` by default.

Examples:

    .. code-block:: python

        # Set the global setting
        pgmock.config.set_safe_mode(True)

        # Only set the configuration while in use of the
        # context manager. Revert it back to the original
        # value when the context manager exits
        with pgmock.config.set_safe_mode(False):
           ...
"""

get_safe_mode = lambda: set_safe_mode.value  # flake8: noqa
"""Returns the configured safe mode"""

set_replace_new_patch_aliases = _ContextableConfigValue(True)
"""Sets whether new patch aliases should be replaced in SQL when found

Since ``pgmock`` turns expressions into ``VALUES`` expressions when patching,
it is not always possible to preserve the original name of what's being patched.

If the name of the expression being patched cannot be used as a valid
patch alias (e.g. a table with a schema name in it), this setting ensures
that all references to the new patch alias will be updated.

This setting primarily applies to SQL in this style::

    SELECT schema.table_name.col from schema.table_name

When patching ``schema.table_name`` with a ``VALUES`` list, it is
impossible to alias the ``VALUES`` list with ``schema.table_name``
since ``.`` is an invalid alias character. To get around this,
``pgmock`` makes the alias of the ``VALUES`` list be the table name
without the schema name. When this setting is turned on, it will
ensure that the ``SELECT schema.table_name.col`` will also be
valid. The patch will look like this when the setting is on::

    SELECT table_name.col from (VALUES(...) AS table_name)

and it will look like this when off::

    SELECT schema.table_name.col from (VALUES(...) AS table_name)

The latter example is invalid SQL, so this setting should be turned
on if the full schema name is present when referencing columns.

.. note::

    This setting incurs a performance overhead
    (10-20% slower depending on the SQL length) only when using the
    ``pgmock.table`` selector.

    This setting does a global search and replace on the query.
    In the example above, it would replace every instance of
    ``schema.table_name.`` with ``table_name.``. Keep this in mind
    as it could potentially have adverse side effects on other
    SQL that might reference the schema and table name followed
    by a period.

    This setting does not handle the case when double quotes are
    used to reference anything (e.g. ``"schema"."table_name"."col"``).

Examples:

    .. code-block:: python

        # Set the global setting
        pgmock.config.set_replace_new_patch_aliases(True)

        # Only set the configuration while in use of the
        # context manager. Revert it back to the original
        # value when the context manager exits
        with pgmock.config.set_replace_new_patch_aliases(False):
            ...
"""

get_replace_new_patch_aliases = lambda: set_replace_new_patch_aliases.value  # flake8: noqa
"""Returns the configured replacement of new patch aliases"""
