hypothesis-graphql
==================

|Build| |Coverage| |Version| |Python versions| |License|

Hypothesis strategies for GraphQL schemas, queries and data.

**NOTE** This package is experimental, some features are not supported yet.

Usage
-----

There are two strategies for different use cases.

1. Schema generation - ``hypothesis_graphql.strategies.schema()``
2. Query - ``hypothesis_graphql.strategies.query(schema)``.

Lets take this schema as an example:

.. code::

    type Book {
      title: String
      author: Author
    }

    type Author {
      name: String
      books: [Book]
    }

    type Query {
      getBooks: [Book]
      getAuthors: [Author]
    }

Then strategies might be used in this way:

.. code:: python

    from hypothesis import given
    from hypothesis_graphql import strategies as gql_st

    SCHEMA = "..."  # the one above

    @given(query=gql_st.query(SCHEMA))
    def test_query(query):
        ...
        # This query might be generated:
        #
        # query {
        #   getBooks {
        #     title
        #   }
        # }

.. |Build| image:: https://github.com/Stranger6667/hypothesis-graphql/workflows/build/badge.svg
   :target: https://github.com/Stranger6667/hypothesis-graphql/actions
.. |Coverage| image:: https://codecov.io/gh/Stranger6667/hypothesis-graphql/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/Stranger6667/hypothesis-graphql/branch/master
   :alt: codecov.io status for master branch
.. |Version| image:: https://img.shields.io/pypi/v/hypothesis-graphql.svg
   :target: https://pypi.org/project/hypothesis-graphql/
.. |Python versions| image:: https://img.shields.io/pypi/pyversions/hypothesis-graphql.svg
   :target: https://pypi.org/project/hypothesis-graphql/
.. |License| image:: https://img.shields.io/pypi/l/hypothesis-graphql.svg
   :target: https://opensource.org/licenses/MIT
