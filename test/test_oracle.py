import graphql

from hypothesis_graphql._strategies.oracle import min_depths, selectable_fields


def schema(sdl):
    return graphql.build_schema(sdl)


def test_selectable_fields_object():
    s = schema("type Query { a: Int b: String }")
    sel = {(name, on) for name, _f, on in selectable_fields(s, s.query_type)}
    assert sel == {("a", None), ("b", None)}


def test_selectable_fields_non_composite():
    s = schema("type Query { a: Int }")
    assert selectable_fields(s, s.get_type("Int")) == []


def test_selectable_fields_interface_includes_impl_only():
    s = schema(
        "type Query { n: Node } interface Node { shared: String } "
        "type Impl implements Node { shared: String only: Int }"
    )
    sel = {(name, on) for name, _f, on in selectable_fields(s, s.get_type("Node"))}
    assert ("shared", None) in sel and ("only", "Impl") in sel


def test_min_depths():
    s = schema("type Query { a: A } type A { f: String g: A }")
    assert min_depths(s)["A"] == 1


def test_selset_values_acyclic():
    from hypothesis_graphql._strategies.oracle import selset_values

    s = schema("type Query { a: Int b: String }")
    vals = selset_values(s, {"Query"}, x=1.0)  # (1+1)(1+1) = 4
    assert abs(vals["Query"] - 4.0) < 1e-9


def test_selset_values_recursive_converges_below_rho():
    from hypothesis_graphql._strategies.oracle import selset_values

    s = schema("type Query { id: ID self: Query }")
    vals = selset_values(s, {"Query"}, x=0.1)
    assert 1.0 < vals["Query"] < 1e6


def test_build_oracle_returns_probabilities():
    from hypothesis_graphql._strategies.oracle import build_oracle

    s = schema("type Query { a: Int b: String c: Query }")
    oracle = build_oracle(s, {"Query"}, target_size=3.0)
    probs = oracle.inclusion_probabilities("Query")
    assert set(probs) == {("a", None), ("b", None), ("c", None)}
    assert all(0.0 < p < 1.0 for p in probs.values())
    assert probs[("c", None)] > 0.05  # composite self-field not p^d-collapsed
