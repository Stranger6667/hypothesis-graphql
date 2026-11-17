import graphql
import pytest
from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from benchmarks._schemas import SCHEMAS, custom_scalars_for
from hypothesis_graphql import Mode, from_schema, mutations, queries

from hypothesis_graphql._strategies.ast import make_query
from hypothesis_graphql._strategies.builder import build_selection_set
from hypothesis_graphql._strategies import sampler
from hypothesis_graphql._strategies.oracle import selectable_fields
from hypothesis_graphql._strategies.sampler import positive_selection
from hypothesis_graphql._strategies.strategy import GraphQLStrategy, _build_alphabet

SCHEMA = graphql.build_schema(
    "type Query { node: Node } type Node { id: ID name: String parent: Node children: [Node] }"
)


def _doc(nodes, schema):
    return make_query(build_selection_set(nodes, type_map=schema.type_map).selections)


@given(data=st.data())
@settings(max_examples=100, suppress_health_check=list(HealthCheck), deadline=None, phases=[Phase.generate])
def test_sampled_queries_are_valid(data):
    nodes = data.draw(positive_selection(SCHEMA, SCHEMA.query_type, _build_alphabet()))
    assert not graphql.validate(SCHEMA, _doc(nodes, SCHEMA))


def test_required_arguments_are_filled():
    s = graphql.build_schema("type Query { f(x: Int!): String }")

    @given(data=st.data())
    @settings(max_examples=50, suppress_health_check=list(HealthCheck), deadline=None, phases=[Phase.generate])
    def run(data):
        nodes = data.draw(positive_selection(s, s.query_type, _build_alphabet()))
        assert not graphql.validate(s, _doc(nodes, s))

    run()


def test_arguments_strategy_is_reused():
    s = graphql.build_schema("type Query { f(x: Int!, y: String): String }")
    gql = GraphQLStrategy(schema=s, alphabet=_build_alphabet())
    args = s.query_type.fields["f"].args
    assert gql.list_of_arguments(args) is gql.list_of_arguments(args)
    # Negative mode passes a fresh dict without the corrupted argument
    assert gql.list_of_arguments({"y": args["y"]}) is gql.list_of_arguments({"y": args["y"]})
    assert gql.list_of_arguments({"y": args["y"]}) is not gql.list_of_arguments(args)


def test_schema_is_walked_once_per_type(monkeypatch):
    calls = []

    def counting(schema, type_):
        calls.append(type_.name)
        return selectable_fields(schema, type_)

    monkeypatch.setattr(sampler, "selectable_fields", counting)
    schema = graphql.build_schema(
        "type Query { node: Node } type Node { id: ID name: String parent: Node children: [Node] }"
    )
    strategy = positive_selection(schema, schema.query_type, _build_alphabet())

    @given(strategy)
    @settings(max_examples=30, suppress_health_check=list(HealthCheck), deadline=None, phases=[Phase.generate])
    def run(_nodes):
        pass

    run()
    assert sorted(calls) == ["Node", "Query"]


def _measure(selection_set):
    # (deepest field nesting, number of field selections)
    depth = count = 0
    for selection in selection_set.selections:
        inner_depth, inner_count = _measure(selection.selection_set) if selection.selection_set else (0, 0)
        if isinstance(selection, graphql.FieldNode):
            inner_depth += 1
            count += 1
        depth = max(depth, inner_depth)
        count += inner_count
    return depth, count


def _sizes(strategy, examples=100):
    sizes = []

    @given(strategy)
    @settings(max_examples=examples, suppress_health_check=list(HealthCheck), deadline=None, phases=[Phase.generate])
    def run(query):
        sizes.append(_measure(graphql.parse(query).definitions[0].selection_set))

    run()
    return sizes


@pytest.mark.parametrize("label", ["recursive", "interface-union"])
@pytest.mark.parametrize(
    ("max_depth", "max_fields"), [(2, 2), (2, 60), (3, 5), (5, 10), (8, 3), (8, 60), (12, 100), (30, 1000)]
)
def test_size_limits(label, max_depth, max_fields):
    sdl = SCHEMAS[label]
    strategy = from_schema(sdl, custom_scalars=custom_scalars_for(sdl), max_depth=max_depth, max_fields=max_fields)
    for depth, count in _sizes(strategy):
        assert 1 <= depth <= max_depth
        assert depth <= count <= max_fields


@pytest.mark.parametrize("max_depth", [2, 3, 4])
def test_max_depth_is_reachable(max_depth):
    sizes = _sizes(queries(SCHEMA, max_depth=max_depth), examples=300)
    assert max(depth for depth, _ in sizes) == max_depth


@pytest.mark.parametrize("max_fields", [2, 4, 7])
def test_max_fields_is_reachable(max_fields):
    sizes = _sizes(queries(SCHEMA, max_fields=max_fields), examples=300)
    assert max(count for _, count in sizes) == max_fields


@pytest.mark.parametrize("factory", [queries, from_schema])
@pytest.mark.parametrize("kwargs", [{"max_depth": 0}, {"max_fields": 0}, {"max_depth": -1}])
def test_size_limits_below_one(factory, kwargs):
    with pytest.raises(InvalidArgument, match="must be at least 1"):
        factory(SCHEMA, **kwargs)
    with pytest.raises(InvalidArgument, match="must be at least 1"):
        factory(SCHEMA, mode=Mode.NEGATIVE, **kwargs)


DEEP = "type Query { a: A x: X } type A { b: B } type B { id: ID } type X { id: ID } type Mutation { m: A }"


@pytest.mark.parametrize(
    ("factory", "kwargs", "message"),
    [
        (queries, {"max_depth": 1}, "`max_depth=1` is too small: the shallowest query needs a depth of 2"),
        (queries, {"max_fields": 1}, "`max_fields=1` is too small: the smallest query needs 2 fields"),
        (
            queries,
            {"max_depth": 2, "fields": ["a"]},
            "`max_depth=2` is too small: the shallowest query needs a depth of 3",
        ),
        (mutations, {"max_fields": 2}, "`max_fields=2` is too small: the smallest query needs 3 fields"),
        (from_schema, {"max_depth": 2}, "`max_depth=2` is too small: the shallowest query needs a depth of 3"),
    ],
)
def test_size_limits_below_schema_minimum(factory, kwargs, message):
    with pytest.raises(InvalidArgument, match=message):
        factory(DEEP, **kwargs)


def test_size_limits_at_schema_minimum():
    assert set(_sizes(queries(DEEP, max_depth=3, max_fields=3, fields=["a"]), examples=20)) == {(3, 3)}
    assert set(_sizes(queries(DEEP, max_depth=2, max_fields=2), examples=20)) == {(2, 2)}


def test_negative_mode_ignores_size_limits():
    schema = "type Query { a(x: Int!): A } type A { b: B } type B { id: ID }"
    with pytest.raises(InvalidArgument):
        queries(schema, max_depth=1, max_fields=1)
    assert _sizes(queries(schema, mode=Mode.NEGATIVE, max_depth=1, max_fields=1), examples=20)


def test_fields_without_leaves_are_never_selected():
    schema = "type Query { a: A x: Int } type A { a: A }"
    assert set(_sizes(queries(schema), examples=30)) == {(1, 1)}
