import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from hypothesis_graphql import mutations


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
    mut = data.draw(mutations(mutation, fields=fields))
    if fields:
        not_selected_fields = ALL_FIELDS - fields
        for field in not_selected_fields:
            assert field not in mut
    validate_operation(mutation, mut)


def test_no_mutation(schema):
    with pytest.raises(InvalidArgument, match="Mutation type is not defined in the schema"):
        mutations(schema)
