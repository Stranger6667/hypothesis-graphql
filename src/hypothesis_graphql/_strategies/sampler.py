from __future__ import annotations

from collections.abc import Sequence

import graphql
from hypothesis import strategies as st

from ..types import CustomScalarStrategies
from .builder import SelectionNode
from .oracle import build_oracle, is_leaf, min_depths, selectable_fields, unwrap
from .strategy import GraphQLStrategy
from .weighted import weighted_boolean

# (name, field, on_type, target, target is a leaf, inclusion strategy)
Entry = tuple[str, graphql.GraphQLField, str | None, graphql.GraphQLNamedType, bool, st.SearchStrategy[bool]]
MAX_DEPTH = 8
MAX_FIELDS = 60


def positive_selection(
    schema: graphql.GraphQLSchema,
    root: graphql.GraphQLObjectType,
    alphabet: st.SearchStrategy[str],
    custom_scalars: CustomScalarStrategies | None = None,
    allow_null: bool = True,
    fields: Sequence[str] | None = None,
) -> st.SearchStrategy[list[SelectionNode]]:
    depths = min_depths(schema)
    # Adaptive expected size: richer queries on larger schemas so big graphs are not under-explored.
    target_size = max(8.0, min(40.0, len(depths) * 0.4))
    oracle = build_oracle(schema, frozenset({root.name}), target_size=target_size)
    gql = GraphQLStrategy(schema=schema, alphabet=alphabet, custom_scalars=custom_scalars or {}, allow_null=allow_null)
    allowed_root = set(fields) if fields else None

    def ok_composite(target: graphql.GraphQLNamedType, depth: int) -> bool:
        md = depths.get(target.name)
        return md is not None and depth + md <= MAX_DEPTH

    plans: dict[str, list[Entry]] = {}

    def plan_for(type_: graphql.GraphQLNamedType) -> list[Entry]:
        plan = plans.get(type_.name)
        if plan is None:
            probs = oracle.inclusion_probabilities(type_.name)
            plan = plans[type_.name] = []
            for name, field, on_type in selectable_fields(schema, type_):
                target = unwrap(field.type)
                plan.append((name, field, on_type, target, is_leaf(target), weighted_boolean(probs[(name, on_type)])))
        return plan

    @st.composite
    def _generate(draw: st.DrawFn) -> list[SelectionNode]:
        counter = [0]

        def select(type_: graphql.GraphQLNamedType, depth: int) -> list[SelectionNode]:
            plan = plan_for(type_)
            if depth == 0 and allowed_root is not None:
                plan = [entry for entry in plan if entry[0] in allowed_root]
            plan = [entry for entry in plan if entry[4] or ok_composite(entry[3], depth)]
            chosen: list[Entry] = []
            for entry in plan:
                # Breadth cap for rare heavy-tail draws.
                if counter[0] >= MAX_FIELDS:  # pragma: no cover
                    break
                if draw(entry[5]):
                    chosen.append(entry)
                    counter[0] += 1
            if not chosen:
                # Only when no field reaches a leaf within MAX_DEPTH.
                if not plan:  # pragma: no cover
                    return []
                # Leaves first so force-one shrinks toward a shallow query.
                chosen = [next((entry for entry in reversed(plan) if entry[4]), plan[0])]
                counter[0] += 1
            nodes: list[SelectionNode] = []
            for name, field, on_type, target, leaf, _ in chosen:
                children = [] if leaf else select(target, depth + 1)
                args = draw(gql.list_of_arguments(field.args))
                nodes.append((name, on_type, children, args))
            return nodes

        return select(root, 0)

    return _generate()
