import graphql
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

type Query {
  getBooks: [Book]
  getAuthors: [Author]
}"""


def test_query():
    @given(query=gql_st.query(SCHEMA))
    def test(query):
        graphql.parse(query)

    test()
