from typing import Dict, Tuple, Union

import graphql
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from ..cache import cached_build_schema
from ..types import CustomScalars


def maybe_parse_schema(schema: Union[str, graphql.GraphQLSchema]) -> graphql.GraphQLSchema:
    if isinstance(schema, str):
        return cached_build_schema(schema)
    return schema


def validate_fields(fields: Tuple[str, ...], available_fields: Dict[str, graphql.GraphQLField]) -> None:
    if not fields:
        raise ValueError("If you pass `fields`, it should not be empty")
    invalid_fields = tuple(field for field in fields if field not in available_fields)
    if invalid_fields:
        raise ValueError(f"Unknown fields: {', '.join(invalid_fields)}")


def validate_custom_scalars(custom_scalars: CustomScalars) -> None:
    assert isinstance(custom_scalars, dict)
    for name, strategy in custom_scalars.items():
        if not isinstance(name, str):
            raise InvalidArgument(f"scalar name {name!r} must be a string")
        if not isinstance(strategy, st.SearchStrategy):
            raise InvalidArgument(
                f"custom_scalars[{name!r}]={strategy!r} must be a Hypothesis "
                "strategy which generates AST nodes matching this scalar."
            )
