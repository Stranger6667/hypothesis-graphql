import graphql

from hypothesis_graphql._strategies.builder import build_selection_set

# SelectionNode = (field_name, on_type, children: list, args: list)


def test_build_flat_selection():
    sel = build_selection_set([("a", None, [], []), ("b", None, [], [])])
    printed = graphql.print_ast(sel)
    assert "a" in printed and "b" in printed


def test_build_aliases_conflicting_fragment_fields():
    s = graphql.build_schema("type Query { r: R } type A { x: Int } type B { x: String } union R = A | B")
    nodes = [("x", "A", [], []), ("x", "B", [], [])]
    printed = graphql.print_ast(build_selection_set(nodes, type_map=s.type_map))
    assert "... on A" in printed and "... on B" in printed and "x_String" in printed
