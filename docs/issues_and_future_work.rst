.. _issues_and_future_work:

Known Issues and Future Work
============================

``pgmock`` has quite a few limitations and issues, some that will be addressed and some things that
are not possible to implement because of limitations in the postgres ``VALUES`` expressions.
These are discussed here along with future work to address issues and make pgmock better.

General Parsing Issues
----------------------

``pgmock`` relies on regular expressions to speedily find and patch relevant SQL expressions. This
has limitations with parsing nested parentheses and ``pgmock`` implements this with custom code.

Using special characters/words in string literals and comments can cause issues for the regular expressions.
For example, this would cause issues when parsing statements since a semicolon is in the comments:

.. code-block:: sql

    STATEMENT 1;
    -- I'm a comment that has a semicolon ; in it
    STATEMENT 2;

For now, ``pgmock`` addresses this issue by allowing *safe* mode to be turned on (`pgmock.config.set_safe_mode`) or
by passing ``safe_mode=True`` to `pgmock.sql` or `pgmock.sql_file`. This mode will strip all SQL of
any string literals or comments to make searching more accurate, but it comes at a cost of performance. In some
cases for really large SQL, performance can be impacted by 50 - 100X slowdowns in pgmock's selector
performance. While this time is still rather small in the context of a test that hits a database, it should
be taken into account when using safe mode.

Other Known Issues
------------------

Here's a short list of some other known issues:

- Subqueries without an alias are currently not supported (e.g. an IN expression). Future versions of ``pgmock`` plan to address this.

- Joins where another keyword comes after the join are currently not supported (e.g. ``JOIN LATERAL``), but future versions plan to address this.

- Using the ``replace_new_patch_aliases`` mode (see `pgmock.config.set_replace_new_patch_aliases`) will not work when using double quotes around selected columns (e.g. ``SELECT "schema"."table"."column" FROM ...``)
