from typing import Dict, Tuple, Union

import graphql

from ..cache import cached_build_schema


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
