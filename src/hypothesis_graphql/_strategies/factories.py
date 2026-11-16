"""Set of function for creating GraphQL nodes.

Most of them exist to avoid using lambdas, which might become expensive in Hypothesis in some cases.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

import graphql

from .. import nodes


@lru_cache
def argument(name: str) -> Callable[[graphql.ValueNode], graphql.ArgumentNode]:
    def factory(value: graphql.ValueNode) -> graphql.ArgumentNode:
        return graphql.ArgumentNode(name=graphql.NameNode(value=name), value=value)

    return factory


@lru_cache
def object_field(name: str) -> Callable[[graphql.ValueNode], graphql.ObjectFieldNode]:
    def factory(value: graphql.ValueNode) -> graphql.ObjectFieldNode:
        return graphql.ObjectFieldNode(name=graphql.NameNode(value=name), value=value)

    return factory


@lru_cache
def null_or_missing_argument(name: str) -> Callable[[bool], graphql.ArgumentNode | None]:
    def factory(is_null: bool) -> graphql.ArgumentNode | None:
        if is_null:
            return graphql.ArgumentNode(name=graphql.NameNode(value=name), value=nodes.Null)
        return None

    return factory
