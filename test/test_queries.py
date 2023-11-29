import graphql
import pytest
from graphql import GraphQLNamedType
from hypothesis import assume, find, given, settings
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from hypothesis_graphql import nodes, queries
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
    query = data.draw(queries(schema))
    validate_operation(schema, query)


@given(data=st.data())
def test_query_subset(data, simple_schema, validate_operation):
    query = data.draw(queries(simple_schema, fields=["getBooks"]))
    validate_operation(simple_schema, query)
    assert "getAuthors" not in query


def test_empty_fields(simple_schema):
    with pytest.raises(ValueError, match="If you pass `fields`, it should not be empty"):
        queries(simple_schema, fields=[])


def test_wrong_fields(simple_schema):
    with pytest.raises(ValueError, match="Unknown fields: wrong"):
        queries(simple_schema, fields=["wrong"])


@given(data=st.data())
def test_query_from_graphql_schema(data, schema, validate_operation):
    query = """type Query {
      getBooksByAuthor(name: String): [Book]
    }"""
    schema = cached_build_schema(schema + query)
    query = data.draw(queries(schema))
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
    query = data.draw(queries(schema))
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
    query = data.draw(queries(schema))
    validate_operation(schema, query)


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
    strategy = queries(schema)
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
    with pytest.raises(InvalidArgument, match="Query type is not defined in the schema"):
        queries(schema)


def test_unknown_type(simple_schema):
    # If there will be a new input type in `graphql`

    schema = cached_build_schema(simple_schema)

    class NewType(GraphQLNamedType):
        pass

    with pytest.raises(TypeError, match="Type NewType is not supported."):
        GraphQLStrategy(schema, alphabet=st.characters()).values(NewType("Test"))


@given(data=st.data())
def test_no_surrogates(data, validate_operation):
    # Unicode surrogates are not supported by GraphQL spec
    schema = """
    type Query {
        hello(user: String!): String
    }
    """
    query = data.draw(queries(schema))
    document = validate_operation(schema, query)
    argument_node = document.definitions[0].selection_set.selections[0].arguments[0]
    assume(argument_node.name.value == "user")
    value = argument_node.value.value
    value.encode("utf8")


ALIASES_INTERFACE_TWO_TYPES = """interface Conflict {
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
}"""
ALIASES_MULTIPLE_INTERFACE_OVERLAP = """interface Nullable {
  value: Float
}
interface Another {
  non_value: Float
}
interface NotNullable {
  value: Float!
}

type First implements Nullable {
  value: Float
}

type Second implements NotNullable & Another {
  value: Float!
  non_value: Float
}

union FirstOrSecond = First | Second

type Query {
  getData: FirstOrSecond!
}"""
ALIASES_INTERFACE_THREE_TYPES = """interface Conflict {
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
}"""
ALIASES_INTERFACE_NESTED_TYPE = """interface Conflict {
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
}"""
ALIASES_UNION_RETURN_TYPE = """type FloatModel {
  query: Float!
}
type StringModel {
  query: String!
}

union Conflict = FloatModel | StringModel

type Query {
  getData: Conflict
}"""
ALIASES_ARGUMENT_ENUM = """interface Conflict {
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
}"""
ALIASES_ARGUMENT_STRING = """interface Conflict {
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
}"""


@pytest.mark.parametrize(
    "schema",
    (
        ALIASES_INTERFACE_TWO_TYPES,
        ALIASES_INTERFACE_THREE_TYPES,
        ALIASES_INTERFACE_NESTED_TYPE,
        ALIASES_MULTIPLE_INTERFACE_OVERLAP,
        ALIASES_UNION_RETURN_TYPE,
        ALIASES_ARGUMENT_ENUM,
        ALIASES_ARGUMENT_STRING,
    ),
    ids=(
        "interface-two-types",
        "interface-three-types",
        "interface-nested-type",
        "non-interface",
        "union",
        "argument-enum",
        "argument-string",
    ),
)
@given(data=st.data())
def test_aliases(data, validate_operation, schema):
    # See GH-49, GH-57
    # When Query contain types on the same level that have fields with the same name but with different types
    query = data.draw(queries(schema))
    # Then no invalid queries should be generated
    validate_operation(schema, query)


def test_custom_printer(simple_schema):
    def printer(node):
        return str(node)

    @given(queries(simple_schema, print_ast=printer))
    @settings(max_examples=1)
    def test(query):
        assert query == "DocumentNode"

    test()


@pytest.mark.parametrize(
    "type_name, default",
    (
        ("String!", '"foo"'),
        ("[String!]", '["foo"]'),
        ("[String!]!", '["foo"]'),
        ("String", "null"),
        ("ID!", "4432841242"),
        ("ID!", '"Foo"'),
        ("[ID!]", '["Foo"]'),
        ("[ID!]", '["Foo", 42]'),
        ("Int!", "4432841"),
        ("[Int!]", "[4432841]"),
        ("Float!", "4432841242.123"),
        ("[Float!]", "[4432841242.123]"),
        ("Date!", '"2022-04-27"'),
        ("[Date!]", '["2022-04-27"]'),
        # These are kind of useless, but covers some code path
        ("Boolean!", "true"),
        ("Color", "null"),
        ("Color!", "GREEN"),
        ("[Color!]", "[GREEN]"),
        ("[Color!]", "null"),
    ),
)
@pytest.mark.parametrize(
    "format_kwargs",
    (
        lambda x: {
            "inner_type_name": x["type_name"],
            "inner_default": x["default"],
            "outer_type_name": x["type_name"],
            "outer_default": x["default"],
        },
        lambda x: {
            "inner_type_name": x["type_name"],
            "inner_default": x["default"],
            "outer_type_name": "InputData!",
            "outer_default": f'{{ inner: {x["default"]} }}',
        },
    ),
)
def test_default_values(validate_operation, type_name, default, format_kwargs):
    # When the input schema contains nodes with default values
    schema = """
scalar Date

enum Color {{
  RED
  GREEN
  BLUE
}}

input InputData {{
  inner: {inner_type_name} = {inner_default},
}}

type Query {{
  getValue(arg: {outer_type_name} = {outer_default}): Int!
}}
    """.format(**format_kwargs({"type_name": type_name, "default": default}))
    strategy = queries(schema, custom_scalars={"Date": st.just("2022-04-26").map(nodes.String)})
    # Then these default values should be used in generated queries

    all_valid = True

    def validate_and_find(query):
        nonlocal all_valid
        try:
            validate_operation(schema, query)
        except AssertionError:
            all_valid = False
        return default in query

    find(strategy, validate_and_find)
    assert all_valid


@given(data=st.data())
def test_empty_interface(data, validate_operation):
    # When the schema contains an empty interface (which is invalid)
    schema = """
interface Empty

type First implements Empty {
  int: Int!
}
type Second implements Empty {
  float: Float!
}

type Query {
  getByEmpty: Empty
}"""
    # Then query generation should not fail
    query = data.draw(queries(schema))
    # And then schema validation should fail instead
    with pytest.raises(TypeError, match="Type Empty must define one or more fields"):
        validate_operation(schema, query)


@given(data=st.data())
def test_custom_strings(data, validate_operation):
    schema = """
type Query {
  getExample(name: String): String
}"""
    query = data.draw(queries(schema, allow_x00=False, codec="ascii"))
    validate_operation(schema, query)
    assert "\0" not in query
    query.encode("ascii")
