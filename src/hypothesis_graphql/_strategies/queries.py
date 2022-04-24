"""Strategies for GraphQL queries."""
from typing import Iterable, Optional, Union

import graphql
from hypothesis import strategies as st

from .ast import make_query
from .context import Context
from .selections import selections
from .validation import maybe_parse_schema, validate_fields


def queries(
    schema: Union[str, graphql.GraphQLSchema], fields: Optional[Iterable[str]] = None
) -> st.SearchStrategy[str]:
    """A strategy for generating valid queries for the given GraphQL schema.

    The output query will contain a subset of fields defined in the `Query` type.

    :param schema: GraphQL schema as a string or `graphql.GraphQLSchema`.
    :param fields: Restrict generated fields to ones in this list.
    """
    parsed_schema = maybe_parse_schema(schema)
    if parsed_schema.query_type is None:
        raise ValueError("Query type is not defined in the schema")
    if fields is not None:
        fields = tuple(fields)
        validate_fields(fields, parsed_schema.query_type.fields)
    context = Context(parsed_schema)
    return selections(context, parsed_schema.query_type, fields=fields).map(make_query).map(graphql.print_ast)
