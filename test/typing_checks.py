from types import MappingProxyType

import graphql
from hypothesis import strategies as st
from typing_extensions import assert_type

from hypothesis_graphql import Mode, from_schema, mutations, nodes, queries, validate_scalar_strategy
from hypothesis_graphql import strategies as gql_st

SCHEMA = "type Query { a(d: Date): Int } type Mutation { b: Int } scalar Date"


def keep(node: graphql.DocumentNode) -> graphql.DocumentNode:
    return node


def keep_any_node(node: graphql.Node) -> graphql.Node:
    return node


assert_type(queries(SCHEMA), st.SearchStrategy[str])
assert_type(mutations(SCHEMA, mode=Mode.NEGATIVE), st.SearchStrategy[str])
assert_type(from_schema(SCHEMA, print_ast=graphql.print_ast), st.SearchStrategy[str])
assert_type(queries(SCHEMA, print_ast=keep), st.SearchStrategy[graphql.DocumentNode])
assert_type(gql_st.queries(SCHEMA, print_ast=keep_any_node), st.SearchStrategy[graphql.Node])
assert_type(gql_st.query(SCHEMA), st.SearchStrategy[str])

dates = {"Date": st.dates().map(nodes.String)}
queries(SCHEMA, custom_scalars=dates)
validate_scalar_strategy("Date", st.dates().map(nodes.String))
queries(SCHEMA, custom_scalars=MappingProxyType(dates))
