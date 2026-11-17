from __future__ import annotations

from collections.abc import Sequence

import graphql

from .._compat import ast_sequence
from ..types import SelectionNodes


def make_document_node(
    selections: SelectionNodes,
    *,
    kind: graphql.OperationType,
    name: graphql.NameNode | None = None,
    fragments: Sequence[graphql.FragmentDefinitionNode] = (),
) -> graphql.DocumentNode:
    """Create top-level node for an operation AST."""
    operation = graphql.OperationDefinitionNode(
        operation=kind,
        name=name,
        variable_definitions=ast_sequence(),
        selection_set=graphql.SelectionSetNode(selections=ast_sequence(selections)),
    )
    return graphql.DocumentNode(definitions=ast_sequence([operation, *fragments]))


def make_query(selections: SelectionNodes) -> graphql.DocumentNode:
    return make_document_node(selections, kind=graphql.OperationType.QUERY)
