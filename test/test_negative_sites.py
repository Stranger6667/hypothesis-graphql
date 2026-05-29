import graphql
from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st

from hypothesis_graphql._strategies.builder import build_selection_set
from hypothesis_graphql._strategies.negative_sites import enumerate_violation_sites, negative_selection
from hypothesis_graphql._strategies.strategy import _build_alphabet


def sites_for(sdl, root="Query"):
    schema = graphql.build_schema(sdl)
    return enumerate_violation_sites(schema, schema.get_type(root))


def _doc(nodes, schema):
    sel = build_selection_set(nodes, type_map=schema.type_map)
    op = graphql.OperationDefinitionNode(
        operation=graphql.OperationType.QUERY, selection_set=sel, variable_definitions=()
    )
    return graphql.DocumentNode(definitions=(op,))


def test_negative_query_is_invalid_at_depth():
    s = graphql.build_schema("type Query { a: A } type A { f(x: Int!): String }")

    @given(data=st.data())
    @settings(max_examples=80, suppress_health_check=list(HealthCheck), deadline=None, phases=[Phase.generate])
    def run(data):
        nodes = data.draw(negative_selection(s, s.query_type, _build_alphabet()))
        doc = _doc(nodes, s)
        assert graphql.validate(s, doc), graphql.print_ast(doc)

    run()


def test_enumerates_root_level_argument_sites():
    sites = sites_for(
        """
        type Query {
          test(value: Int!): String
          getUser(id: ID!): String
        }
        """
    )
    located = {(s.field_path, s.arg_name) for s in sites}
    assert (("test",), "value") in located
    assert (("getUser",), "id") in located
    assert all(s.depth == 1 for s in sites)


def test_enumerates_nested_argument_sites_at_their_depth():
    sites = sites_for(
        """
        type Query { a: A }
        type A { f(x: Int!): String }
        """
    )
    by_path = {s.field_path: s.depth for s in sites}
    assert by_path[("a", "f")] == 2


def test_descends_into_interface_implementations_via_fragments():
    sites = sites_for(
        """
        type Query { node: Node }
        interface Node { shared(a: Int!): String }
        type Impl implements Node { shared(a: Int!): String only(b: Int!): String }
        """
    )
    by = {(s.field_path, s.arg_name): s for s in sites}
    assert by[(("node", "shared"), "a")].path[-1].on_type is None
    assert by[(("node", "only"), "b")].path[-1].on_type == "Impl"


def test_descends_into_union_members_via_fragments():
    sites = sites_for(
        """
        type Query { result: Result }
        type A { fa(x: Int!): String }
        type B { fb(y: Int!): String }
        union Result = A | B
        """
    )
    by = {s.field_path: s for s in sites}
    assert by[("result", "fa")].path[-1].on_type == "A"
    assert by[("result", "fb")].path[-1].on_type == "B"
