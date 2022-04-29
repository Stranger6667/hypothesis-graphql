import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from hypothesis_graphql import from_schema

QUERY = """type Query {
  getBooks: [Book]
  getAuthors: [Author]
}"""
MUTATION = """type Mutation {
    addBook(title: String!, author: String!): Book!
    addAuthor(name: String!): Author!
}"""
QUERY_FIELDS = ["getBooks", "getAuthors"]
MUTATION_FIELDS = ["addBook", "addAuthor"]


@pytest.mark.parametrize(
    "types, available_fields",
    (
        (QUERY, QUERY_FIELDS),
        (MUTATION, MUTATION_FIELDS),
        (f"{QUERY}\n{MUTATION}", QUERY_FIELDS + MUTATION_FIELDS),
    ),
)
@given(data=st.data())
def test_from_schema(data, schema, validate_operation, types, available_fields):
    # When the `from_schema` constructor is used
    schema += f"\n{types}"
    selected_fields = data.draw(st.lists(st.sampled_from(available_fields), min_size=1, unique=True))
    other_fields = [field for field in available_fields if field not in selected_fields]
    # Then it should generate both, queries & mutations
    query = data.draw(from_schema(schema, fields=selected_fields))
    for field in other_fields:
        assert field not in query
    # Just Mutation without Query is an invalid schema, but still can generate data
    # Validate other schemas that are assumed to be valid
    if types != MUTATION:
        validate_operation(schema, query)


def test_no_query_no_mutation(schema, validate_operation):
    with pytest.raises(InvalidArgument, match="Query or Mutation type must be provided"):
        from_schema(schema)
