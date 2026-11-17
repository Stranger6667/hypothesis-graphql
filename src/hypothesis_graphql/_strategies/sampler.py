from __future__ import annotations

from collections.abc import Sequence
from operator import itemgetter

import graphql
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from ..types import CustomScalarStrategies
from .builder import SelectionNode
from .oracle import build_oracle, is_leaf, min_depths, selectable_fields, unwrap
from .strategy import GraphQLStrategy
from .weighted import weighted_boolean

# (name, field, on_type, target, target is a leaf, inclusion strategy, fewest fields the entry adds)
Entry = tuple[str, graphql.GraphQLField, str | None, graphql.GraphQLNamedType, bool, st.SearchStrategy[bool], int]


def positive_selection(
    schema: graphql.GraphQLSchema,
    root: graphql.GraphQLObjectType,
    alphabet: st.SearchStrategy[str],
    custom_scalars: CustomScalarStrategies | None = None,
    allow_null: bool = True,
    fields: Sequence[str] | None = None,
    max_depth: int = 9,
    max_fields: int = 60,
) -> st.SearchStrategy[list[SelectionNode]]:
    depths = min_depths(schema)
    # Adaptive expected size: richer queries on larger schemas so big graphs are not under-explored.
    # Kept below `max_fields`, otherwise most draws hit the cap and drop the fields declared last.
    target_size = min(max(8.0, min(40.0, len(depths) * 0.4)), max_fields * 2 / 3)
    oracle = build_oracle(schema, frozenset({root.name}), target_size=target_size)
    gql = GraphQLStrategy(schema=schema, alphabet=alphabet, custom_scalars=custom_scalars or {}, allow_null=allow_null)

    plans: dict[str, list[Entry]] = {}

    def plan_for(type_: graphql.GraphQLNamedType) -> list[Entry]:
        plan = plans.get(type_.name)
        if plan is None:
            probs = oracle.inclusion_probabilities(type_.name)
            plan = plans[type_.name] = []
            for name, field, on_type in selectable_fields(schema, type_):
                target = unwrap(field.type)
                leaf = is_leaf(target)
                # The shortest chain down to a leaf has one field per level
                below = 0 if leaf else depths.get(target.name)
                if below is not None:
                    plan.append(
                        (name, field, on_type, target, leaf, weighted_boolean(probs[(name, on_type)]), below + 1)
                    )
        return plan

    root_plan = plan_for(root)
    if fields:
        allowed_root = set(fields)
        root_plan = [entry for entry in root_plan if entry[0] in allowed_root]
    smallest = min((entry[6] for entry in root_plan), default=1)
    if max_depth < smallest:
        raise InvalidArgument(f"`max_depth={max_depth}` is too small: the shallowest query needs a depth of {smallest}")
    if max_fields < smallest:
        raise InvalidArgument(f"`max_fields={max_fields}` is too small: the smallest query needs {smallest} fields")

    @st.composite
    def _generate(draw: st.DrawFn) -> list[SelectionNode]:
        # Fields left to hand out; every chosen entry takes its fewest-fields cost up front
        budget = max_fields

        def select(plan: list[Entry], depth: int, reserved: int) -> list[SelectionNode]:
            nonlocal budget
            budget += reserved
            chosen: list[Entry] = []
            for entry in plan:
                cost = entry[6]
                if cost <= budget and depth + cost <= max_depth and draw(entry[5]):
                    chosen.append(entry)
                    budget -= cost
            if not chosen:
                # Only when no field reaches a leaf.
                if not plan:  # pragma: no cover
                    return []
                # Leaves first so force-one shrinks toward a shallow query; the cheapest entry always fits.
                forced = next((entry for entry in reversed(plan) if entry[4]), None) or min(plan, key=itemgetter(6))
                chosen.append(forced)
                budget -= forced[6]
            nodes: list[SelectionNode] = []
            for name, field, on_type, target, leaf, _, cost in chosen:
                children = [] if leaf else select(plan_for(target), depth + 1, cost - 1)
                args = draw(gql.list_of_arguments(field.args))
                nodes.append((name, on_type, children, args))
            return nodes

        return select(root_plan, 0, 0)

    return _generate()
