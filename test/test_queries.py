import graphql
import pytest
from graphql import GraphQLNamedType
from hypothesis import assume, find, given, settings
from hypothesis import strategies as st

from hypothesis_graphql import strategies as gql_st
from hypothesis_graphql._strategies.strategy import GraphQLStrategy
from hypothesis_graphql.cache import cached_build_schema


@pytest.fixture(scope="session")
def simple_schema(schema):
    return (
        schema
        + """type Query {
          getBooks: [Book]
          getAuthors: [Author]
        }"""
    )


@pytest.mark.parametrize(
    "query_type",
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
@given(data=st.data())
def test_query(data, schema, query_type, validate_operation):
    schema = schema + query_type
    query = data.draw(gql_st.queries(schema))
    validate_operation(schema, query)


@given(data=st.data())
def test_query_subset(data, simple_schema, validate_operation):
    query = data.draw(gql_st.queries(simple_schema, fields=["getBooks"]))
    validate_operation(simple_schema, query)
    assert "getAuthors" not in query


def test_empty_fields(simple_schema):
    with pytest.raises(ValueError, match="If you pass `fields`, it should not be empty"):
        gql_st.queries(simple_schema, fields=[])


def test_wrong_fields(simple_schema):
    with pytest.raises(ValueError, match="Unknown fields: wrong"):
        gql_st.queries(simple_schema, fields=["wrong"])


@given(data=st.data())
def test_query_from_graphql_schema(data, schema, validate_operation):
    query = """type Query {
      getBooksByAuthor(name: String): [Book]
    }"""
    schema = cached_build_schema(schema + query)
    query = data.draw(gql_st.queries(schema))
    validate_operation(schema, query)


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
        ("contains: RequiredInput", ("ObjectValueNode",)),
        ("contains: NestedQueryInput", ("ObjectValueNode",)),
    ),
)
@given(data=st.data())
def test_arguments(data, schema, arguments, node_names, notnull, validate_operation):
    if notnull:
        arguments += "!"
    query_type = f"""type Query {{
      getModel({arguments}): Model
    }}"""

    schema = schema + query_type
    query = data.draw(gql_st.queries(schema))
    validate_operation(schema, query)
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


@pytest.mark.parametrize(
    "query_type",
    (
        "type Query { getModel: Node }",
        "type Query { getModel: Alone }",
    ),
)
@given(data=st.data())
def test_interface(data, schema, query_type, validate_operation):
    schema = schema + query_type
    parsed_schema = cached_build_schema(schema)
    query = data.draw(gql_st.queries(schema))
    validate_operation(parsed_schema, query)


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
def test_minimal_queries(query, schema, minimum):
    schema = schema + f"type Query {{ {query} }}"
    strategy = gql_st.queries(schema)
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
        gql_st.queries(schema)


def test_unknown_type(simple_schema):
    # If there will be a new input type in `graphql`

    schema = cached_build_schema(simple_schema)

    class NewType(GraphQLNamedType):
        pass

    with pytest.raises(TypeError, match="Type NewType is not supported."):
        GraphQLStrategy(schema).values(NewType("Test"))


@given(data=st.data())
def test_no_surrogates(data, validate_operation):
    # Unicode surrogates are not supported by GraphQL spec
    schema = """
    type Query {
        hello(user: String!): String
    }
    """
    query = data.draw(gql_st.queries(schema))
    document = validate_operation(schema, query)
    argument_node = document.definitions[0].selection_set.selections[0].arguments[0]
    assume(argument_node.name.value == "user")
    value = argument_node.value.value
    value.encode("utf8")


@pytest.mark.parametrize(
    "schema",
    (
        """interface Conflict {
          id: ID
        }

        type FloatModel implements Conflict {
          id: ID,
          query: Float!
        }

        type StringModel implements Conflict {
          id: ID,
          query: String!
        }

        type Query {
          getData: Conflict
        }""",
        """interface Conflict {
          id: ID!
        }

        type First implements Conflict {
          id: ID!
          key: String
        }

        type Second implements Conflict {
          id: ID!
          key: String
        }

        type Third implements Conflict {
          id: ID!
          key: [String]
        }

        type Query {
          getData: Conflict
        }""",
        """interface Conflict {
          keywords: [Keyword!]!
        }

        type First implements Conflict {
          keywords: [Keyword!]!
        }

        type Keyword {
          values(first: Int): String!
        }

        type Query {
          getData(input: Int!): Conflict
        }""",
        """type FloatModel {
          query: Float!
        }
        type StringModel {
          query: String!
        }

        union Conflict = FloatModel | StringModel

        type Query {
          getData: Conflict
        }""",
        """interface Conflict {
          query(arg: Arg): String!
        }

        type FirstModel implements Conflict {
          query(arg: Arg): String!
        }

        type SecondModel implements Conflict {
          query(arg: Arg): String!
        }

        enum Arg {
          First
          Second
        }

        type Query {
          getConflict(arg: String!): Conflict!
        }""",
        """interface Conflict {
          query(arg: String): String!
        }

        type FirstModel implements Conflict {
          query(arg: String): String!
        }

        type SecondModel implements Conflict {
          query(arg: String): String!
        }

        type Query {
          getConflict(arg: String!): Conflict!
        }""",
    ),
    ids=("interface", "interface-multiple-types", "interface-sub-type", "union", "arguments-enum", "arguments-string"),
)
@given(data=st.data())
def test_conflicting_field_types(data, validate_operation, schema):
    # See GH-49, GH-57
    # When Query contain types on the same level that have fields with the same name but with different types
    query = data.draw(gql_st.queries(schema))
    # Then no invalid queries should be generated
    validate_operation(schema, query)


def test_custom_printer(simple_schema):
    def printer(node):
        return str(node)

    @given(gql_st.queries(simple_schema, print_ast=printer))
    @settings(max_examples=1)
    def test(query):
        assert query == "DocumentNode"

    test()
