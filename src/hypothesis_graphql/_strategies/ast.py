from __future__ import annotations

import graphql

from .._compat import ast_sequence
from ..types import SelectionNodes


def make_document_node(selections: SelectionNodes, *, kind: graphql.OperationType) -> graphql.DocumentNode:
    """Create top-level node for an operation AST."""
    return graphql.DocumentNode(
        definitions=ast_sequence(
            [
                graphql.OperationDefinitionNode(
                    operation=kind,
                    variable_definitions=ast_sequence(),
                    selection_set=graphql.SelectionSetNode(selections=ast_sequence(selections)),
                )
            ]
        ),
    )


def make_query(selections: SelectionNodes) -> graphql.DocumentNode:
    return make_document_node(selections, kind=graphql.OperationType.QUERY)


def make_mutation(selections: SelectionNodes) -> graphql.DocumentNode:
    return make_document_node(selections, kind=graphql.OperationType.MUTATION)
