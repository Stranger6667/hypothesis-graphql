import math

import graphql

from hypothesis_graphql._strategies.oracle import build_oracle, min_depths, selectable_fields


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
    s = schema("type Query { a: Int b: String c: Query }")
    oracle = build_oracle(s, {"Query"}, target_size=3.0)
    probs = oracle.inclusion_probabilities("Query")
    assert set(probs) == {("a", None), ("b", None), ("c", None)}
    assert all(0.0 < p < 1.0 for p in probs.values())
    assert probs[("c", None)] > 0.05  # composite self-field not p^d-collapsed


def test_min_depths_is_cached_per_schema():
    s = schema("type Query { a: A } type A { f: String g: A }")
    assert min_depths(s) is min_depths(s)


def test_build_oracle_is_cached_per_schema_and_roots():
    s = schema("type Query { a: Int b: String c: Query }")
    first = build_oracle(s, frozenset({"Query"}), target_size=3.0)
    second = build_oracle(s, frozenset({"Query"}), target_size=3.0)
    assert first is second


def test_build_oracle_resolves_target_size_on_slowly_converging_schema():
    s = schema("type Query { next: Mid } type Mid { next: Tree } type Tree { id: ID left: Tree right: Tree }")

    def root_value(x):
        # Least root of `u = 1 + x * (tree - 1)` where `tree = (1 + x) * u ** 2`; `Query = 1 + x * (u - 1)`
        u = (1 - math.sqrt(1 - 4 * x * (1 + x) * (1 - x))) / (2 * x * (1 + x))
        return 1 + x * (u - 1)

    def size(x):
        h = x * 1e-4
        return x * (math.log(root_value(x + h)) - math.log(root_value(x - h))) / (2 * h)

    oracle = build_oracle(s, frozenset({"Query"}), target_size=8.0)
    # The fixpoint needs several thousand sweeps this close to the singularity
    assert size(oracle.x) < 8.0 <= size(oracle.x + 2**-19)
    assert abs(oracle.y["Query"] - root_value(oracle.x)) < 1e-9


def test_build_oracle_on_densely_self_recursive_type():
    s = schema("type Query { a: Int b: Query c: Query d: Query e: Query f: Query }")
    oracle = build_oracle(s, frozenset({"Query"}), target_size=8.0)
    x, y = oracle.x, oracle.y["Query"]
    composite = 1 + x * (y - 1)
    assert y > 1.0
    assert abs(y - (1 + x) * composite**5) < 1e-8
    # Expected selection size, from differentiating the fixpoint equation
    size = (x / (1 + x) + 5 * x * (y - 1) / composite) / (1 - 5 * x * y / composite)
    assert 7.0 < size < 8.0
