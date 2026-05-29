from typing import List, Optional, Sequence

import graphql
from hypothesis import strategies as st

from ..types import CustomScalarStrategies
from .builder import SelectionNode
from .oracle import Selectable, build_oracle, is_leaf, min_depths, selectable_fields, unwrap
from .strategy import GraphQLStrategy
from .weighted import weighted_boolean

MAX_DEPTH = 8
MAX_FIELDS = 60


def positive_selection(
    schema: graphql.GraphQLSchema,
    root: graphql.GraphQLObjectType,
    alphabet: st.SearchStrategy[str],
    custom_scalars: Optional[CustomScalarStrategies] = None,
    allow_null: bool = True,
    fields: Optional[Sequence[str]] = None,
) -> st.SearchStrategy[List[SelectionNode]]:
    depths = min_depths(schema)
    # Adaptive expected size: richer queries on larger schemas so big graphs are not under-explored.
    target_size = max(8.0, min(40.0, len(depths) * 0.4))
    oracle = build_oracle(schema, frozenset({root.name}), target_size=target_size)
    gql = GraphQLStrategy(schema=schema, alphabet=alphabet, custom_scalars=custom_scalars or {}, allow_null=allow_null)
    allowed_root = set(fields) if fields else None

    def ok_composite(target: graphql.GraphQLNamedType, depth: int) -> bool:
        md = depths.get(target.name)
        return md is not None and depth + md <= MAX_DEPTH

    def fields_at(type_: graphql.GraphQLNamedType, depth: int) -> List[Selectable]:
        items = selectable_fields(schema, type_)
        if depth == 0 and allowed_root is not None:
            items = [item for item in items if item[0] in allowed_root]
        return items

    @st.composite  # type: ignore
    def _generate(draw: st.DrawFn) -> List[SelectionNode]:
        counter = [0]

        def select(type_: graphql.GraphQLNamedType, depth: int) -> List[SelectionNode]:
            probs = oracle.inclusion_probabilities(type_.name)
            chosen: List[Selectable] = []
            for name, field, on_type in fields_at(type_, depth):
                target = unwrap(field.type)
                if not is_leaf(target) and not ok_composite(target, depth):
                    continue
                # Breadth cap for rare heavy-tail draws.
                if counter[0] >= MAX_FIELDS:  # pragma: no cover
                    break
                if draw(weighted_boolean(probs[(name, on_type)])):
                    chosen.append((name, field, on_type))
                    counter[0] += 1
            if not chosen:
                valid: List[Selectable] = []
                for name, field, on_type in fields_at(type_, depth):
                    target = unwrap(field.type)
                    if is_leaf(target):
                        # Leaves first so force-one shrinks toward a shallow query.
                        valid.insert(0, (name, field, on_type))
                    elif ok_composite(target, depth):
                        valid.append((name, field, on_type))
                # Only when no field reaches a leaf within MAX_DEPTH.
                if not valid:  # pragma: no cover
                    return []
                chosen = [valid[0]]
                counter[0] += 1
            nodes: List[SelectionNode] = []
            for name, field, on_type in chosen:
                target = unwrap(field.type)
                children = [] if is_leaf(target) else select(target, depth + 1)
                args = draw(gql.list_of_arguments(field.args))
                nodes.append((name, on_type, children, args))
            return nodes

        return select(root, 0)

    return _generate()
