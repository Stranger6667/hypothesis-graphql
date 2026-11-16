from __future__ import annotations

import dataclasses
import math
from functools import lru_cache
from typing import cast

import graphql

Selectable = tuple[str, graphql.GraphQLField, str | None]


def unwrap(type_: graphql.GraphQLType) -> graphql.GraphQLNamedType:
    while isinstance(type_, graphql.GraphQLWrappingType):
        type_ = type_.of_type
    return cast(graphql.GraphQLNamedType, type_)


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


OVERFLOW = 1e9
TOLERANCE = 1e-10
SETTLED = 1e-12
DIVERGING = 1.01
MAX_RATE = 0.999

# For each reachable composite type: name, number of leaf fields, indices of composite field targets
Equations = tuple[list[str], list[int], list[list[int]]]


def _equations(schema: graphql.GraphQLSchema, roots: frozenset[str]) -> Equations:
    # Post-order: targets precede the types selecting them, so one in-place sweep carries values up acyclic paths.
    rows: dict[str, tuple[int, list[str]]] = {}
    names: list[str] = []
    stack = [(name, False) for name in roots]
    while stack:
        name, expanded = stack.pop()
        if expanded:
            names.append(name)
        elif name not in rows:
            leaves, children = 0, []
            for _name, field, _on_type in selectable_fields(schema, schema.type_map[name]):
                target = unwrap(field.type)
                if is_leaf(target):
                    leaves += 1
                else:
                    children.append(target.name)
            rows[name] = (leaves, children)
            stack.append((name, True))
            stack.extend((child, False) for child in children)
    index = {name: idx for idx, name in enumerate(names)}
    return names, [rows[name][0] for name in names], [[index[child] for child in rows[name][1]] for name in names]


def _solve(equations: Equations, x: float, start: list[float] | None = None) -> list[float]:
    # Least fixpoint >= 1 of y_T = product over selectable fields of (1 + phi). The right-hand side is monotone
    # and convex in y, so in-place sweeps from all-ones (or from a solution for a smaller x) only increase:
    # they either converge or grow without bound, which means x is past the singularity.
    _, leaves, targets = equations
    y = [1.0] * len(leaves) if start is None else start.copy()
    leaf_products = [(1.0 + x) ** count for count in leaves]
    deltas = [0.0] * len(leaves)
    comparable = False
    while True:
        change = 0.0
        # Smallest ratio between a type's move in this sweep and in the previous one
        rate = math.inf
        for idx, product in enumerate(leaf_products):
            for target in targets[idx]:
                product *= 1.0 + x * (y[target] - 1.0)
            if product > OVERFLOW:
                raise OverflowError
            delta = product - y[idx]
            previous = deltas[idx]
            relative = abs(delta) / product
            if relative > change:
                change = relative
            # Moves at rounding-noise level say nothing about the rate
            if previous > SETTLED * product:
                if delta < rate * previous:
                    rate = delta / previous
            elif delta < 0.0 and relative > SETTLED:
                rate = 0.0
            deltas[idx] = delta
            y[idx] = product
        if change < TOLERANCE:
            return y
        if comparable and 0.0 < rate < math.inf:
            # By convexity every later sweep moves each type by at least `rate` times its previous move
            if rate > DIVERGING:
                raise OverflowError
            # The geometric series of the remaining moves stays at or below the fixpoint; adding it skips most
            # sweeps when convergence is slow. The cap keeps rounding errors in `rate` from overshooting.
            rate = min(rate, MAX_RATE)
            rest = rate / (1.0 - rate)
            y = [value + delta * rest for value, delta in zip(y, deltas, strict=True)]
            comparable = False
        else:
            comparable = rate > 0.0


def selset_values(schema: graphql.GraphQLSchema, roots: frozenset[str], x: float) -> dict[str, float]:
    equations = _equations(schema, frozenset(roots))
    return dict(zip(equations[0], _solve(equations, x), strict=True))


@lru_cache(maxsize=32)
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
            for _name, field, _on_type in selectable_fields(schema, schema.type_map[name]):
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
        for name, field, on_type in selectable_fields(self.schema, self.schema.type_map[type_name]):
            target = unwrap(field.type)
            phi = self.x if is_leaf(target) else self.x * (self.y.get(target.name, 0.0) - 1.0)
            out[(name, on_type)] = phi / (1.0 + phi)
        return out


def build_oracle(schema: graphql.GraphQLSchema, roots: frozenset[str], target_size: float = 8.0) -> Oracle:
    # `roots` may arrive as a plain `set`; normalize before it hits the cache key below.
    return _build_oracle_cached(schema, frozenset(roots), target_size)


@lru_cache(maxsize=32)
def _build_oracle_cached(schema: graphql.GraphQLSchema, roots: frozenset[str], target_size: float) -> Oracle:
    equations = _equations(schema, roots)
    root = equations[0].index(next(iter(roots)))
    lo, hi, best_x = 1e-6, 1.0, 1e-6
    # Solution slightly below `best_x`: a valid `start` for every later probe
    below: list[float] | None = None
    for _ in range(20):
        mid = (lo + hi) / 2
        h = mid * 1e-4
        try:
            y_lo = _solve(equations, mid - h, below)
            y_hi = _solve(equations, mid + h, y_lo)
        except OverflowError:
            hi = mid
            continue
        if mid * (math.log(y_hi[root]) - math.log(y_lo[root])) / (2 * h) < target_size:
            best_x, lo, below = mid, mid, y_lo
        else:
            hi = mid
    return Oracle(schema=schema, x=best_x, y=dict(zip(equations[0], _solve(equations, best_x, below), strict=True)))
