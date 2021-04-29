import graphql
import pytest
from graphql import GraphQLNamedType
from hypothesis import HealthCheck, assume, find, given, settings

from hypothesis_graphql import strategies as gql_st
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

input EnumInput {
  color: Color
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


@pytest.fixture
def simple_schema():
    return (
        SCHEMA
        + """type Query {
          getBooks: [Book]
          getAuthors: [Author]
        }"""
    )


def validate_query(schema, query):
    query_ast = graphql.parse(query)
    errors = graphql.validate(schema, query_ast)
    assert not errors


def assert_schema(schema):
    if isinstance(schema, str):
        parsed_schema = graphql.build_schema(schema)
    else:
        parsed_schema = schema

    @given(query=gql_st.query(schema))
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test(query):
        validate_query(parsed_schema, query)

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


def test_query_subset(simple_schema):
    parsed_schema = graphql.build_schema(simple_schema)

    @given(query=gql_st.query(simple_schema, fields=["getBooks"]))
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test(query):
        validate_query(parsed_schema, query)
        assert "getAuthors" not in query

    test()


def test_empty_fields(simple_schema):
    with pytest.raises(ValueError, match="If you pass `fields`, it should not be empty"):
        gql_st.query(simple_schema, fields=[])


def test_wrong_fields(simple_schema):
    with pytest.raises(ValueError, match="Unknown fields: wrong"):
        gql_st.query(simple_schema, fields=["wrong"])


def test_query_from_graphql_schema():
    query = """type Query {
      getBooksByAuthor(name: String): [Book]
    }"""
    schema = graphql.build_schema(SCHEMA + query)
    assert_schema(schema)


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
        ("color: EnumInput", ("EnumValueNode",)),
        ("contain: [Int]", ("ListValueNode", "IntValueNode")),
        ("contain: [Int!]", ("ListValueNode", "IntValueNode")),
        ("contain: [Float]", ("ListValueNode", "FloatValueNode")),
        ("contain: [Float!]", ("ListValueNode", "FloatValueNode")),
        ("contain: [String]", ("ListValueNode", "StringValueNode")),
        ("contain: [String!]", ("ListValueNode", "StringValueNode")),
        ("contain: [Boolean]", ("ListValueNode", "BooleanValueNode")),
        ("contain: [Boolean!]", ("ListValueNode", "BooleanValueNode")),
        ("contain: [Color]", ("ListValueNode", "EnumValueNode")),
        ("contain: [Color!]", ("ListValueNode", "EnumValueNode")),
        ("contain: [[Int]]", ("ListValueNode", "IntValueNode")),
        ("contain: [[Int]!]", ("ListValueNode", "IntValueNode")),
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

    schema = SCHEMA + query_type
    parsed_schema = graphql.build_schema(schema)

    @given(query=gql_st.query(schema))
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test(query):
        validate_query(parsed_schema, query)
        for node_name in node_names:
            assert node_name not in query
        if notnull:
            assert "getModel(" in query
        parsed = graphql.parse(query)
        selection = parsed.definitions[0].selection_set.selections[0]
        if notnull:
            # there should be one argument if it is not null
            assert len(selection.arguments) == 1
        # at least one Model field is selected
        assert len(selection.selection_set.selections) > 0

    test()


@pytest.mark.parametrize(
    "query, minimum",
    (
        (
            "getAuthors: [Author]",
            "",
        ),
        (
            "getAuthors(value: Int!): [Author]",
            "(value: 0)",
        ),
        (
            "getAuthors(value: Float!): [Author]",
            "(value: 0.0)",
        ),
        (
            "getAuthors(value: String!): [Author]",
            '(value: "")',
        ),
        (
            "getAuthors(value: Color!): [Author]",
            "(value: RED)",
        ),
    ),
)
def test_minimal_queries(query, minimum):
    schema = SCHEMA + f"type Query {{ {query} }}"
    strategy = gql_st.query(schema)
    minimal_query = f"""{{
  getAuthors{minimum} {{
    name
  }}
}}"""
    assert find(strategy, lambda x: True).strip() == minimal_query


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


CUSTOM_SCALAR_TEMPLATE = """
scalar Date

type Object {{
  created: Date
}}
type Query {{
  {query}
}}
"""


def test_custom_scalar_non_argument():
    # When a custom scalar type is defined
    # And is used in a non-argument position

    schema = CUSTOM_SCALAR_TEMPLATE.format(query="getObjects: [Object]")
    parsed_schema = graphql.build_schema(schema)

    @given(query=gql_st.query(schema))
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test(query):
        validate_query(parsed_schema, query)
        # Then queries should be generated
        assert "created" in query

    test()


def test_custom_scalar_argument_nullable():
    # When a custom scalar type is defined
    # And is used in an argument position
    # And is nullable
    # And there are no other arguments

    num_of_queries = 0

    schema = CUSTOM_SCALAR_TEMPLATE.format(query="getByDate(created: Date): Object")
    parsed_schema = graphql.build_schema(schema)

    @given(query=gql_st.query(schema))
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test(query):
        nonlocal num_of_queries

        num_of_queries += 1
        validate_query(parsed_schema, query)
        assert "getByDate {" in query

    test()
    # Then only one query should be generated
    assert num_of_queries == 1


def test_custom_scalar_argument():
    # When a custom scalar type is defined
    # And is used in an argument position
    # And is not nullable

    @given(query=gql_st.query(CUSTOM_SCALAR_TEMPLATE.format(query="getByDate(created: Date!): Object")))
    def test(query):
        pass

    with pytest.raises(TypeError, match="Non-nullable custom scalar types are not supported as arguments"):
        test()


def test_no_surrogates():
    # Unicode surrogates are not supported by GraphQL spec
    schema = """
    type Query {
        hello(user: String!): String
    }
    """
    parsed_schema = graphql.build_schema(schema)

    @given(query=gql_st.query(schema))
    def test(query):
        validate_query(parsed_schema, query)
        document = graphql.parse(query)
        argument_node = document.definitions[0].selection_set.selections[0].arguments[0]
        assume(argument_node.name.value == "user")
        value = argument_node.value.value
        value.encode("utf8")

    test()
