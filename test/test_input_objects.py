import inspect

import graphql
import pytest
from hypothesis import HealthCheck, Phase, find, given, settings
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from hypothesis_graphql import from_schema, nodes
from hypothesis_graphql._strategies.strategy import GraphQLStrategy

ONE_OF_SUPPORTED = "is_one_of" in inspect.signature(graphql.GraphQLInputObjectType).parameters
ONE_OF = "input Pick @oneOf { id: ID, name: String, tags: [String!], nested: Pick, filter: Filter }" * ONE_OF_SUPPORTED
SDL = f"""
enum Color {{ RED GREEN BLUE }}
input Range {{ gte: Int! lte: Int! step: Int = 10 }}
input Filter {{
  color: Color = RED
  range: Range
  ranges: [Range!]
  and: [Filter!]
  not: Filter
  name: String!
}}
{ONE_OF}
type Query {{ search(filter: Filter{", pick: Pick" * ONE_OF_SUPPORTED}): Int }}
"""
SCHEMA = graphql.build_schema(SDL)
GENERATE_ONLY = settings(
    max_examples=100, suppress_health_check=list(HealthCheck), deadline=None, phases=[Phase.generate], database=None
)


def make(sdl=SDL, **kwargs):
    schema = graphql.build_schema(sdl)
    return schema, GraphQLStrategy(schema, alphabet=st.characters(), **kwargs)


def draw_many(strategy, count):
    out = []

    @settings(GENERATE_ONLY, max_examples=count)
    @given(strategy)
    def inner(value):
        out.append(value)

    inner()
    return out


@pytest.mark.parametrize(
    "name",
    ["Filter", "Range", pytest.param("Pick", marks=pytest.mark.skipif(not ONE_OF_SUPPORTED, reason="no `@oneOf`"))],
)
def test_no_strategies_built_after_warm_up(monkeypatch, name):
    schema, gql = make()
    calls = []
    original = GraphQLStrategy.values

    def values(self, type_, default=None):
        calls.append(str(type_))
        return original(self, type_, default)

    monkeypatch.setattr(GraphQLStrategy, "values", values)
    strategy = gql.objects(schema.type_map[name], nullable=False)
    draw_many(strategy, 200)
    warm = len(calls)
    # Every field of every reachable input type is built at most once per (type, default) pair
    assert warm <= 20
    draw_many(strategy, 200)
    assert len(calls) == warm


@GENERATE_ONLY
@given(from_schema(SDL))
def test_values_validate(query):
    assert not graphql.validate(SCHEMA, graphql.parse(query)), query


@GENERATE_ONLY
@given(st.data())
def test_required_fields_always_present(data):
    schema, gql = make()
    node = data.draw(gql.objects(schema.type_map["Filter"], nullable=False))
    names = [field.name.value for field in node.fields]
    assert "name" in names
    assert len(names) == len(set(names))
    for field in node.fields:
        if field.name.value == "range" and isinstance(field.value, graphql.ObjectValueNode):
            assert {"gte", "lte"} <= {inner.name.value for inner in field.value.fields}


@pytest.mark.parametrize("name", ["color", "range", "ranges", "and", "not"])
def test_optional_fields_present_and_absent(name):
    schema, gql = make()
    strategy = gql.objects(schema.type_map["Filter"], nullable=False)
    find(strategy, lambda node: any(field.name.value == name for field in node.fields))
    find(strategy, lambda node: all(field.name.value != name for field in node.fields))


def test_default_is_generated():
    schema, gql = make()
    strategy = gql.objects(schema.type_map["Range"], nullable=False)
    default = schema.type_map["Range"].fields["step"].ast_node.default_value
    # Equal default nodes share one cached scalar strategy, hence equality instead of identity
    find(strategy, lambda node: any(field.value == default for field in node.fields))


def test_unsupported_scalar_on_required_field():
    schema, gql = make("scalar Custom input In { a: Custom! b: Int } type Query { f(x: In): Int }")
    strategy = gql.objects(schema.type_map["In"], nullable=False)
    with pytest.raises(InvalidArgument, match="Custom"):
        draw_many(strategy, 5)


@GENERATE_ONLY
@given(st.data())
def test_unsupported_scalar_on_optional_field_is_skipped(data):
    schema, gql = make("scalar Custom input In { a: Custom b: Int c: Custom } type Query { f(x: In): Int }")
    node = data.draw(gql.objects(schema.type_map["In"], nullable=False))
    assert [field.name.value for field in node.fields] == ["b"]


@GENERATE_ONLY
@given(st.data())
def test_custom_scalar(data):
    schema, gql = make(
        "scalar Custom input In { a: Custom! } type Query { f(x: In): Int }",
        custom_scalars={"Custom": st.just(nodes.Int(7))},
    )
    node = data.draw(gql.objects(schema.type_map["In"], nullable=False))
    assert [(field.name.value, field.value.value) for field in node.fields] == [("a", "7")]


@pytest.mark.skipif(not ONE_OF_SUPPORTED, reason="no `@oneOf`")
@GENERATE_ONLY
@given(st.data())
def test_one_of_has_exactly_one_non_null_field(data):
    schema, gql = make()
    node = data.draw(gql.objects(schema.type_map["Pick"], nullable=False))
    assert len(node.fields) == 1
    assert not isinstance(node.fields[0].value, graphql.NullValueNode)
