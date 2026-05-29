from __future__ import annotations

import dataclasses
import math

import graphql

Selectable = tuple[str, graphql.GraphQLField, str | None]


def unwrap(type_: graphql.GraphQLType) -> graphql.GraphQLNamedType:
    while isinstance(type_, graphql.GraphQLWrappingType):
        type_ = type_.of_type
    return type_


def is_leaf(type_: graphql.GraphQLNamedType) -> bool:
    return isinstance(type_, (graphql.GraphQLScalarType, graphql.GraphQLEnumType))


def selectable_fields(schema: graphql.GraphQLSchema, type_: graphql.GraphQLNamedType) -> list[Selectable]:
    out: list[Selectable] = []
    if isinstance(type_, graphql.GraphQLObjectType):
        for name, field in type_.fields.items():
            out.append((name, field, None))
    elif isinstance(type_, graphql.GraphQLInterfaceType):
        for name, field in type_.fields.items():
            out.append((name, field, None))
        for impl in schema.get_implementations(type_).objects:
            for name, field in impl.fields.items():
                if name not in type_.fields:
                    out.append((name, field, impl.name))
    elif isinstance(type_, graphql.GraphQLUnionType):
        for member in type_.types:
            for name, field in member.fields.items():
                out.append((name, field, member.name))
    return out


MAX_ITERS = 1000
OVERFLOW = 1e9


def _reachable_composites(schema: graphql.GraphQLSchema, roots: frozenset) -> set:
    # Roots and every appended target are composite (only non-leaf field types are pushed).
    seen: set = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        for _name, field, _on_type in selectable_fields(schema, schema.get_type(name)):
            target = unwrap(field.type)
            if not is_leaf(target):
                stack.append(target.name)
    return seen


# type name -> list of (is_leaf, target type name) for each selectable field
FieldTerms = dict[str, list[tuple[bool, str]]]


def _field_terms(schema: graphql.GraphQLSchema, types: set) -> FieldTerms:
    terms: FieldTerms = {}
    for name in types:
        row: list[tuple[bool, str]] = []
        for _name, field, _on_type in selectable_fields(schema, schema.get_type(name)):
            target = unwrap(field.type)
            row.append((True, "") if is_leaf(target) else (False, target.name))
        terms[name] = row
    return terms


def _solve(types: set, terms: FieldTerms, x: float) -> dict[str, float]:
    # Fixpoint of y_T = product over selectable fields of (1 + phi); non-convergence within
    # MAX_ITERS is treated as past the singularity (OverflowError), so callers back x off.
    y = dict.fromkeys(types, 0.0)
    for _ in range(MAX_ITERS):
        updated = {}
        for name in types:
            product = 1.0
            for is_leaf_field, target_name in terms[name]:
                phi = x if is_leaf_field else x * (y[target_name] - 1.0)
                product *= 1.0 + phi
                if product > OVERFLOW:
                    raise OverflowError(name)
            updated[name] = product
        if all(abs(updated[name] - y[name]) < 1e-12 for name in types):
            return updated
        y = updated
    raise OverflowError("no convergence")


def selset_values(schema: graphql.GraphQLSchema, roots: frozenset, x: float) -> dict[str, float]:
    types = _reachable_composites(schema, roots)
    return _solve(types, _field_terms(schema, types), x)


def min_depths(schema: graphql.GraphQLSchema) -> dict[str, int | None]:
    # Shortest number of selection levels from a type to a leaf field; None if unreachable.
    # Bellman-Ford-style fixpoint over the type graph -- order-independent.
    composites = [
        name
        for name, type_ in schema.type_map.items()
        if isinstance(type_, (graphql.GraphQLObjectType, graphql.GraphQLInterfaceType, graphql.GraphQLUnionType))
    ]
    depth: dict[str, int | None] = dict.fromkeys(composites)
    changed = True
    while changed:
        changed = False
        for name in composites:
            best = depth[name]
            for _name, field, _on_type in selectable_fields(schema, schema.get_type(name)):
                target = unwrap(field.type)
                if is_leaf(target):
                    candidate: int | None = 1
                else:
                    child_depth = depth.get(target.name)
                    candidate = None if child_depth is None else child_depth + 1
                if candidate is not None and (best is None or candidate < best):
                    best = candidate
            if best != depth[name]:
                depth[name] = best
                changed = True
    return depth


@dataclasses.dataclass(slots=True)
class Oracle:
    schema: graphql.GraphQLSchema
    x: float
    y: dict[str, float]

    def inclusion_probabilities(self, type_name: str) -> dict[tuple[str, str | None], float]:
        out: dict[tuple[str, str | None], float] = {}
        for name, field, on_type in selectable_fields(self.schema, self.schema.get_type(type_name)):
            target = unwrap(field.type)
            phi = self.x if is_leaf(target) else self.x * (self.y.get(target.name, 0.0) - 1.0)
            out[(name, on_type)] = phi / (1.0 + phi)
        return out


def build_oracle(schema: graphql.GraphQLSchema, roots: frozenset, target_size: float = 8.0) -> Oracle:
    # Precompute field terms once; the binary search below reuses them across all solves.
    types = _reachable_composites(schema, roots)
    terms = _field_terms(schema, types)
    root = next(iter(roots))

    def size_at(x: float) -> float:
        h = x * 1e-4
        hi = _solve(types, terms, x + h)
        lo = _solve(types, terms, x - h)
        return x * (math.log(hi[root]) - math.log(lo[root])) / (2 * h)

    lo, hi, best_x = 1e-6, 1.0, 1e-6
    for _ in range(20):
        mid = (lo + hi) / 2
        try:
            size = size_at(mid)
        except OverflowError:
            hi = mid
            continue
        if size < target_size:
            best_x, lo = mid, mid
        else:
            hi = mid
    return Oracle(schema=schema, x=best_x, y=_solve(types, terms, best_x))
