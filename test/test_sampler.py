import graphql
from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st

from hypothesis_graphql._strategies.builder import build_selection_set
from hypothesis_graphql._strategies.sampler import positive_selection
from hypothesis_graphql._strategies.strategy import _build_alphabet

SCHEMA = graphql.build_schema(
    "type Query { node: Node } type Node { id: ID name: String parent: Node children: [Node] }"
)


def _doc(nodes, schema):
    sel = build_selection_set(nodes, type_map=schema.type_map)
    op = graphql.OperationDefinitionNode(
        operation=graphql.OperationType.QUERY, selection_set=sel, variable_definitions=()
    )
    return graphql.DocumentNode(definitions=(op,))


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
