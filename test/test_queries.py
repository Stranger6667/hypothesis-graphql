import graphql
import pytest
from hypothesis import given

import hypothesis_graphql.strategies as gql_st

SCHEMA = """
type Book {
  title: String
  author: Author
}

type Author {
  name: String
  books: [Book]
}
"""


def assert_schema(schema):
    @given(query=gql_st.query(schema))
    def test(query):
        graphql.parse(query)

    test()


@pytest.mark.parametrize(
    "query",
    (
        """type Query {
      getBooks: [Book]
      getAuthors: [Author]
    }""",
    ),
)
def test_query(query):
    assert_schema(SCHEMA + query)


def test_missing_query():
    schema = """type Author {
      name: String
    }"""
    with pytest.raises(ValueError, match="Query type is not defined in the schema"):
        gql_st.query(schema)
