import json

import graphql
import pytest
from graphql.execution.values import get_argument_values, get_variable_values
from hypothesis import given, settings
from hypothesis import strategies as st

from benchmarks._schemas import SCHEMAS, custom_scalars_for
from hypothesis_graphql import Mode, mutations, queries
from hypothesis_graphql._strategies.variables import extract_variables

SCHEMA = graphql.build_schema(
    """
scalar JSON
enum Color { RED GREEN }
input Filter { color: Color, limit: Int!, tags: [String!] }
interface Node { id: ID! }
type User implements Node {
  id: ID!
  name(upper: Boolean): String
  friends(first: Int = 10, id: ID): [User!]
  id_2(id: ID): ID
}
type Query {
  user(id: ID!): User
  node(id: ID!): Node
  users(filter: Filter, ids: [ID!], big: Float, meta: JSON, color: Color): [User!]
  count(value: Int!): Int
}
type Mutation { rename(id: ID!, name: String!): User }
"""
)
SMALL = """
enum Color { RED GREEN BLUE }
input EnumInput { color: Color }
input QueryInput { eq: String, ne: String }
input RequiredInput { eq: Float! }
input NestedQueryInput { code: QueryInput }
type Image { path(size: Int): String }
type Video { duration(unit: String): Int }
union Media = Image | Video
interface Node { id: ID }
type Book implements Node { id: ID, title(upper: Boolean): String, related(first: Int = 3, color: Color): [Book!] }
type Query {
  getBooks(filter: NestedQueryInput, required: RequiredInput!, color: Color, colors: [EnumInput!]): [Book]
  getBook(id: ID!, int: Int, float: Float, string: String, boolean: Boolean, ints: [[Int!]]): Book
  node(id: ID): Node
  media(limit: Int = 5): [Media]
}
type Mutation { addBook(title: String!, input: QueryInput): Book }
"""


def transform(query, schema=SCHEMA):
    document = graphql.parse(query, no_location=True)
    before = graphql.print_ast(document)
    new, variables = extract_variables(document, schema)
    assert graphql.print_ast(document) == before
    return graphql.print_ast(new), variables


def collapse(query):
    return " ".join(query.split())


def normalize(query):
    return collapse(graphql.print_ast(graphql.parse(query)))


def coerce_variables(schema, document, variables):
    """Coerced variables per operation and all coercion errors."""
    values, errors = [], []
    for definition in document.definitions:
        if isinstance(definition, graphql.OperationDefinitionNode):
            coerced = get_variable_values(schema, definition.variable_definitions or [], variables)
            (errors if isinstance(coerced, list) else values).append(coerced)
    return values, errors


def argument_values(schema, document, variables=None):
    type_info = graphql.TypeInfo(schema)
    values = []

    class Collector(graphql.Visitor):
        def enter_field(self, node, *_):
            field = type_info.get_field_def()
            if field is not None:
                values.append((node.name.value, get_argument_values(field, node, variables)))

    graphql.visit(document, graphql.TypeInfoVisitor(type_info, Collector()))
    return values


def assert_equivalent(schema, document):
    new, variables = extract_variables(document, schema)
    json.dumps(variables)
    assert graphql.validate(schema, new) == [], graphql.print_ast(new)
    (coerced,), errors = coerce_variables(schema, new, variables)
    assert not errors
    assert argument_values(schema, new, coerced) == argument_values(schema, document)
    return new, variables


def test_simple():
    query, variables = transform('{ user(id: "1") { name } }')
    assert collapse(query) == normalize("query ($id: ID!) { user(id: $id) { name } }")
    assert variables == {"id": "1"}


def test_no_arguments():
    document = graphql.parse("{ user { name } }")
    new, variables = extract_variables(document, SCHEMA)
    assert graphql.print_ast(new) == graphql.print_ast(document)
    assert variables == {}


def test_unique_names():
    query, variables = transform(
        """{
  user(id: 1) { friends(id: 2) { friends(id: 3) { id_2(id: 4) } } }
  node(id: 5) { ... on User { friends(id: 6, first: 7) { id } } }
}"""
    )
    assert variables == {"id": 1, "id_2": 2, "id_3": 3, "id_4": 4, "id_5": 5, "id_6": 6, "first": 7}
    assert "($id: ID!, $id_2: ID, $id_3: ID, $id_4: ID, $id_5: ID!, $id_6: ID, $first: Int)" in query
    assert "friends(id: $id_6, first: $first)" in query
    assert graphql.validate(SCHEMA, graphql.parse(query)) == []


def test_equal_literals_share_a_variable():
    # Fields merge only when their arguments are identical
    query, variables = transform(
        '{ user(id: "1") { name } user(id: "1") { id friends(id: "1") { id } } node(id: "1") { id } count(value: 1) }'
    )
    assert collapse(query) == normalize(
        "query ($id: ID!, $id_2: ID, $value: Int!) "
        "{ user(id: $id) { name } user(id: $id) { id friends(id: $id_2) { id } } node(id: $id) { id } count(value: $value) }"
    )
    assert variables == {"id": "1", "id_2": "1", "value": 1}
    assert graphql.validate(SCHEMA, graphql.parse(query)) == []


def test_values():
    query, variables = transform(
        """{ users(
  filter: {color: RED, limit: 3, tags: ["a", "b"]}, ids: [1, "2"], big: 9223372036854775807,
  meta: {a: [1, 2.5, null, true, B], c: 12345678901234567890}, color: null
) { id } }"""
    )
    assert variables == {
        "filter": {"color": "RED", "limit": 3, "tags": ["a", "b"]},
        "ids": [1, "2"],
        "big": 9223372036854775807,
        "meta": {"a": [1, 2.5, None, True, "B"], "c": 12345678901234567890},
        "color": None,
    }
    assert json.loads(json.dumps(variables)) == variables
    assert "($filter: Filter, $ids: [ID!], $big: Float, $meta: JSON, $color: Color)" in query
    assert_equivalent(SCHEMA, graphql.parse(query))


def test_shared_nodes_are_not_mutated():
    from hypothesis_graphql import nodes
    from hypothesis_graphql._compat import ast_sequence
    from hypothesis_graphql._strategies.ast import make_query

    shared = {"color": nodes.Enum("RED"), "meta": nodes.Boolean(True), "big": nodes.Null}
    arguments = [graphql.ArgumentNode(name=graphql.NameNode(value=name), value=value) for name, value in shared.items()]
    field = graphql.FieldNode(
        name=graphql.NameNode(value="users"),
        arguments=ast_sequence(arguments),
        directives=ast_sequence(),
        selection_set=graphql.SelectionSetNode(
            selections=ast_sequence([graphql.FieldNode(name=graphql.NameNode(value="id"), arguments=ast_sequence())])
        ),
    )
    document = make_query([field])
    before = graphql.print_ast(document)
    new, variables = extract_variables(document, SCHEMA)
    assert variables == {"color": "RED", "meta": True, "big": None}
    assert graphql.print_ast(document) == before
    assert [argument.value for argument in arguments] == list(shared.values())
    assert_equivalent(SCHEMA, document)


def test_directives_aliases_and_operation_name():
    query, variables = transform(
        """query Named @live(if: true) {
  me: user(id: "1") @include(if: true) { name(upper: true) @skip(if: false) }
}"""
    )
    assert collapse(query) == normalize(
        "query Named($id: ID!, $upper: Boolean) @live(if: true) "
        "{ me: user(id: $id) @include(if: true) { name(upper: $upper) @skip(if: false) } }"
    )
    assert variables == {"id": "1", "upper": True}


def test_fragment_definitions_stay_inline():
    query, variables = transform(
        """query Q { user(id: "1") { ...F ... { friends(first: 2) { id } } } }
fragment F on User { other: friends(first: 3) { name(upper: true) } }"""
    )
    assert collapse(query) == normalize(
        "query Q($id: ID!, $first: Int) { user(id: $id) { ...F ... { friends(first: $first) { id } } } } "
        "fragment F on User { other: friends(first: 3) { name(upper: true) } }"
    )
    assert variables == {"id": "1", "first": 2}
    assert graphql.validate(SCHEMA, graphql.parse(query)) == []


def test_unknown_fields_and_arguments_stay_inline():
    query, variables = transform(
        """{
  user(id: "1", extra: 2) { unknown(a: 1) { deeper(b: 2) } ... on Missing { name(upper: true) } }
  missing(c: 3)
  __type(name: "User") { name }
}"""
    )
    assert variables == {"id": "1"}
    for inline in ("extra: 2", "unknown(a: 1)", "deeper(b: 2)", "name(upper: true)", "missing(c: 3)", '"User"'):
        assert inline in query


def test_existing_variables_are_kept():
    query, variables = transform(
        'query ($id: ID!, $limit: Int!) { user(id: $id) { friends(id: "2") { id } } users(filter: {limit: $limit}) { id } }'
    )
    assert collapse(query) == normalize(
        "query ($id: ID!, $limit: Int!, $id_2: ID) "
        "{ user(id: $id) { friends(id: $id_2) { id } } users(filter: {limit: $limit}) { id } }"
    )
    assert variables == {"id_2": "2"}


def test_multiple_operations():
    query, variables = transform('query A { user(id: "1") { id } } mutation B { rename(id: "2", name: "x") { id } }')
    assert collapse(query) == normalize(
        "query A($id: ID!) { user(id: $id) { id } } "
        "mutation B($id_2: ID!, $name: String!) { rename(id: $id_2, name: $name) { id } }"
    )
    assert variables == {"id": "1", "id_2": "2", "name": "x"}


def test_duplicate_arguments_stay_duplicate():
    query, variables = transform("{ count(value: 1, value: 1) count(value: 2, value: 3) }")
    assert "count(value: $value, value: $value)" in query
    assert "count(value: $value_2, value: $value_3)" in query
    assert graphql.validate(SCHEMA, graphql.parse(query)) != []


def test_missing_root_type():
    query, variables = transform("subscription { user(id: 1) { id } }")
    assert variables == {}
    assert "user(id: 1)" in query


@pytest.mark.parametrize(
    "query",
    [
        # A variable would coerce these values although the literals are invalid
        "{ count(value: 1.0) }",
        '{ users(color: "RED") { id } }',
        '{ users(filter: {color: "RED", limit: 1}) { id } }',
        "{ users(filter: {limit: 1.0}) { id } }",
        # Duplicate input fields collapse in a JSON object
        "{ users(filter: {limit: 1, limit: 1}) { id } }",
        "{ users(meta: [{a: 1, a: 2}]) { id } }",
    ],
)
def test_invalid_literal_valid_as_variable_stays_inline(query):
    new, variables = transform(query)
    assert variables == {}
    assert collapse(new) == normalize(query)
    assert graphql.validate(SCHEMA, graphql.parse(new)) != []


@pytest.mark.parametrize(
    "query",
    [
        '{ count(value: "a") }',
        "{ count(value: null) }",
        "{ count(value: 12345678901234567890) }",
        "{ users(color: BLUE) { id } }",
        "{ users(filter: {color: RED}) { id } }",
        "{ users(filter: {limit: 1, unknown: 2}) { id } }",
    ],
)
def test_invalid_literal_becomes_invalid_variable(query):
    document = graphql.parse(query)
    assert graphql.validate(SCHEMA, document) != []
    new, variables = extract_variables(document, SCHEMA)
    assert len(variables) == 1
    assert graphql.validate(SCHEMA, new) == []
    assert coerce_variables(SCHEMA, new, variables)[1]


def cases():
    for name, sdl in [("small", SMALL), *SCHEMAS.items()]:
        schema = graphql.build_schema(sdl)
        for factory, root in ((queries, schema.query_type), (mutations, schema.mutation_type)):
            if root is not None:
                yield pytest.param(sdl, schema, factory, id=f"{name}-{factory.__name__}")


@pytest.mark.parametrize(("sdl", "schema", "factory"), cases())
def test_positive_documents_are_equivalent(sdl, schema, factory):
    seen = []

    @given(factory(sdl, custom_scalars=custom_scalars_for(sdl), print_ast=lambda document: document))
    @settings(max_examples=100)
    def test(document):
        _, variables = assert_equivalent(schema, document)
        seen.append(len(variables))

    test()
    # Schemas without any field argument have nothing to extract
    if graphql.print_schema(schema).count("(") > 0:
        assert any(seen)


@pytest.mark.parametrize(("sdl", "schema", "factory"), cases())
def test_negative_documents_stay_invalid(sdl, schema, factory):
    try:
        strategy = factory(sdl, custom_scalars=custom_scalars_for(sdl), mode=Mode.NEGATIVE, print_ast=lambda d: d)
        strategy.validate()
    except Exception as exc:
        pytest.skip(f"No negative strategy: {exc}")

    @given(st.data())
    @settings(max_examples=100)
    def test(data):
        document = data.draw(strategy)
        new, variables = extract_variables(document, schema)
        json.dumps(variables)
        assert graphql.validate(schema, new) or coerce_variables(schema, new, variables)[1], graphql.print_ast(document)

    test()
