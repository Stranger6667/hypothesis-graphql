import graphql
from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st

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
