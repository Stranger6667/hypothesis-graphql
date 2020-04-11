"""Strategies for GraphQL queries."""
from functools import partial
from typing import List, Optional, Tuple

import graphql
from hypothesis import strategies as st


def query(schema: str) -> st.SearchStrategy[str]:
    parsed_schema = graphql.build_schema(schema)
    if parsed_schema.query_type is None:
        raise ValueError("Query type is not defined in the schema")
    return fields(parsed_schema.query_type).map(make_query).map(graphql.print_ast)


def fields(object_type: graphql.GraphQLObjectType) -> st.SearchStrategy[List[graphql.FieldNode]]:
    """Generate a subset of fields defined on the given type."""
    # minimum 1 field, an empty query is not valid
    field_pairs = tuple(object_type.fields.items())
    # pairs are unique by field name
    return st.lists(st.sampled_from(field_pairs), min_size=1, unique_by=lambda x: x[0]).flatmap(list_of_field_nodes)


make_selection_set_node = partial(graphql.SelectionSetNode, kind="selection_set")


def make_query(selections: List[graphql.FieldNode]) -> graphql.DocumentNode:
    """Create top-level node for a query AST."""
    return graphql.DocumentNode(  # type: ignore
        kind="document",
        definitions=[
            graphql.OperationDefinitionNode(
                kind="operation_definition",
                operation=graphql.OperationType.QUERY,
                selection_set=make_selection_set_node(selections=selections),
            )
        ],
    )


def list_of_field_nodes(items: List[Tuple[str, graphql.GraphQLField]]) -> st.SearchStrategy[List[graphql.FieldNode]]:
    """Generate a list of `graphql.FieldNode`."""
    return st.tuples(*(field_nodes(name, field) for name, field in items)).map(list)


def field_nodes(name: str, field: graphql.GraphQLField) -> st.SearchStrategy[graphql.FieldNode]:
    """Generate a single field node with optional children."""
    return st.builds(
        partial(graphql.FieldNode, name=graphql.NameNode(value=name)),  # type: ignore
        selection_set=st.builds(make_selection_set_node, selections=fields_for_type(field)),
    )


def fields_for_type(field: graphql.GraphQLField) -> st.SearchStrategy[Optional[List[graphql.FieldNode]]]:
    """Extract proper type from the field and generate field nodes for this type."""
    type_ = field.type
    if isinstance(type_, graphql.GraphQLScalarType):
        return st.none()
    if isinstance(type_, graphql.GraphQLList):
        type_ = type_.of_type
    # TODO. handle other types, e.g. GraphQLEnumType
    return fields(type_)  # type: ignore
