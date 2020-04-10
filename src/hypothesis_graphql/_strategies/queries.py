"""Strategies for GraphQL queries."""
from typing import Dict, List, Optional

import graphql
from hypothesis import strategies as st


def query(schema: str) -> st.SearchStrategy:
    parsed_schema = graphql.build_schema(schema)
    if parsed_schema.query_type is None:
        raise ValueError("Query type is not defined in the schema")
    return get_strategy_for_type(parsed_schema.query_type).map(make_query).map(graphql.print_ast)


def get_strategy_for_type(object_type: graphql.GraphQLObjectType) -> st.SearchStrategy:
    # minimum 1 field, an empty query is not valid
    fields = list(object_type.fields.items())
    return st.lists(st.sampled_from(fields), min_size=1, unique_by=lambda x: x[0]).flatmap(
        lambda items: st.fixed_dictionaries({name: handle_field(field) for name, field in items})
    )


def handle_field(field: graphql.GraphQLField) -> st.SearchStrategy:
    type_ = field.type
    if isinstance(type_, graphql.GraphQLScalarType):
        return st.none()
    if isinstance(type_, graphql.GraphQLList):
        type_ = type_.of_type
    # TODO. handle other types, e.g. GraphQLEnumType
    return get_strategy_for_type(type_)  # type: ignore


def make_query(tree: Dict[str, Optional[Dict]]) -> graphql.DocumentNode:
    # TODO. build it on the way, without traversing the tree again
    return graphql.DocumentNode(  # type: ignore
        kind="document",
        definitions=[
            graphql.OperationDefinitionNode(
                kind="operation_definition",
                operation=graphql.OperationType.QUERY,
                selection_set=graphql.SelectionSetNode(kind="selection_set", selections=build_tree(tree)),
            )
        ],
    )


def build_tree(tree: Dict[str, Optional[Dict]]) -> List[graphql.FieldNode]:
    return [
        graphql.FieldNode(  # type: ignore
            name=graphql.NameNode(value=name),
            selection_set=graphql.SelectionSetNode(kind="selection_set", selections=build_tree(value))
            if value
            else None,
        )
        for name, value in tree.items()
    ]
