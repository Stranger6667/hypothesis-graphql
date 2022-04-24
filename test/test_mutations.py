import pytest
from hypothesis import given
from hypothesis import strategies as st

from hypothesis_graphql import strategies as gql_st


@pytest.fixture(scope="session")
def mutation(schema):
    return f"""{schema}
type Query {{
  getBooks: [Book]
  getAuthors: [Author]
}}
type Mutation {{
    addBook(title: String!, author: String!): Book!
    addAuthor(name: String!): Author!
    }}"""


ALL_FIELDS = {"addBook", "addAuthor"}


@pytest.mark.parametrize("fields", (None, {"addBook"}, {"addAuthor"}))
@given(data=st.data())
def test_mutation(data, mutation, validate_operation, fields):
    mut = data.draw(gql_st.mutations(mutation, fields=fields))
    if fields:
        not_selected_fields = ALL_FIELDS - fields
        for field in not_selected_fields:
            assert field not in mut
    validate_operation(mutation, mut)


def test_no_mutation(schema):
    with pytest.raises(ValueError, match="Mutation type is not defined in the schema"):
        gql_st.mutations(schema)