import graphql

from ..types import SelectionNodes


def make_document_node(selections: SelectionNodes, *, kind: graphql.OperationType) -> graphql.DocumentNode:
    """Create top-level node for an operation AST."""
    return graphql.DocumentNode(
        kind="document",
        definitions=[
            graphql.OperationDefinitionNode(
                kind="operation_definition",
                operation=kind,
                selection_set=graphql.SelectionSetNode(kind="selection_set", selections=selections),
            )
        ],
    )


def make_query(selections: SelectionNodes) -> graphql.DocumentNode:
    return make_document_node(selections, kind=graphql.OperationType.QUERY)


def make_mutation(selections: SelectionNodes) -> graphql.DocumentNode:
    return make_document_node(selections, kind=graphql.OperationType.MUTATION)
