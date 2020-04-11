import graphql
import pytest
from graphql import GraphQLNamedType
from hypothesis import given

import hypothesis_graphql.strategies as gql_st
from hypothesis_graphql._strategies.queries import value_nodes

SCHEMA = """
type Book {
  title: String
  author: Author
}

type Author {
  name: String
  books: [Book]
}

enum Color {
  RED
  GREEN
  BLUE
}

input QueryInput {
  eq: String
  ne: String
}

input NestedQueryInput {
  code: QueryInput
}

type Model {
  int: Int,
  float: Float,
  string: String
  id: ID,
  boolean: Boolean
  color: Color
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
        """type Query {
      getBooksByAuthor(name: String): [Book]
    }""",
    ),
)
def test_query(query):
    assert_schema(SCHEMA + query)


@pytest.mark.parametrize("notnull", (True, False))
@pytest.mark.parametrize(
    "arguments, node_names",
    (
        ("int: Int", ("IntValueNode",)),
        ("float: Float", ("FloatValueNode",)),
        ("string: String", ("StringValueNode",)),
        ("id: ID", ("IntValueNode", "StringValueNode")),
        ("boolean: Boolean", ("BooleanValueNode",)),
        ("color: Color", ("EnumValueNode",)),
        ("contain: [Int]", ("ListValueNode", "IntValueNode")),
        ("contain: [Float]", ("ListValueNode", "FloatValueNode")),
        ("contain: [String]", ("ListValueNode", "StringValueNode")),
        ("contain: [Boolean]", ("ListValueNode", "BooleanValueNode")),
        ("contain: [Color]", ("ListValueNode", "EnumValueNode")),
        ("contain: [[Int]]", ("ListValueNode", "IntValueNode")),
        ("contains: QueryInput", ("ObjectValueNode",)),
        ("contains: NestedQueryInput", ("ObjectValueNode",)),
    ),
)
def test_arguments(arguments, node_names, notnull):
    if notnull:
        arguments += "!"
    query_type = f"""type Query {{
      getModel({arguments}): Model
    }}"""

    @given(query=gql_st.query(SCHEMA + query_type))
    def test(query):
        for node_name in node_names:
            assert node_name not in query
        if notnull:
            assert "getModel(" in query
        graphql.parse(query)

    test()


def test_missing_query():
    schema = """type Author {
      name: String
    }"""
    with pytest.raises(ValueError, match="Query type is not defined in the schema"):
        gql_st.query(schema)


def test_unknown_type():
    # If there will be a new input type in `graphql`

    class NewType(GraphQLNamedType):
        pass

    with pytest.raises(TypeError, match="Type NewType is not supported."):
        value_nodes(NewType("Test"))


def test_custom_scalar():
    # custom scalar types are not supported directly
    schema = """
    scalar Date

    type Object {
      created: Date
    }

    type Query {
      getByDate(created: Date): Object
    }
    """

    @given(query=gql_st.query(schema))
    def test(query):
        pass

    with pytest.raises(TypeError, match="Custom scalar types are not supported"):
        test()
