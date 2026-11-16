from __future__ import annotations

from typing import Any, TypeVar

import graphql

from .._compat import ast_sequence

N = TypeVar("N", bound=graphql.Node)
# `value_from_ast` accepts literals of a mismatched kind (`1.0` for `Int`) in `graphql-core` 3.3
_coerce_literal = getattr(graphql, "coerce_input_literal", graphql.value_from_ast)


def extract_variables(
    document: graphql.DocumentNode, schema: graphql.GraphQLSchema
) -> tuple[graphql.DocumentNode, dict[str, Any]]:
    """Replace field-argument literals with variables; return the new document and the JSON values of its variables."""
    variables: dict[str, Any] = {}
    # One `variables` object serves every operation of the document, so names are unique document-wide
    used = {
        definition.variable.name.value
        for operation in document.definitions
        if isinstance(operation, graphql.OperationDefinitionNode)
        for definition in operation.variable_definitions or ()
    }
    variable_definitions: list[graphql.VariableDefinitionNode] = []
    # Fields with the same response name merge only if their arguments are identical, so equal literals share a variable
    shared: dict[tuple[str, str, str], graphql.VariableNode] = {}

    def argument(node: graphql.ArgumentNode, arg: graphql.GraphQLArgument | None) -> graphql.ArgumentNode:
        if arg is None or _is_inline_only(node.value):
            return node
        key = (node.name.value, str(arg.type), graphql.print_ast(node.value))
        variable = shared.get(key)
        if variable is None:
            value = graphql.value_from_ast_untyped(node.value)
            # An invalid literal whose plain value coerces (`1.0` for `Int`, `"RED"` for an enum) is valid as a variable
            if _coerce_literal(node.value, arg.type) is graphql.Undefined and _coerces(value, arg.type):
                return node
            name, suffix = node.name.value, 1
            while name in used:
                suffix += 1
                name = f"{node.name.value}_{suffix}"
            used.add(name)
            variables[name] = value
            variable = shared[key] = graphql.VariableNode(name=graphql.NameNode(value=name))
            variable_definitions.append(
                graphql.VariableDefinitionNode(
                    variable=variable, type=graphql.parse_type(key[1]), directives=ast_sequence()
                )
            )
        return _replace(node, value=variable)

    def selection_set(
        node: graphql.SelectionSetNode, parent: graphql.GraphQLNamedType | None
    ) -> graphql.SelectionSetNode:
        selections: list[graphql.SelectionNode] = []
        for selection in node.selections:
            if isinstance(selection, graphql.FieldNode):
                field = (
                    parent.fields.get(selection.name.value)
                    if isinstance(parent, (graphql.GraphQLObjectType, graphql.GraphQLInterfaceType))
                    else None
                )
                changes: dict[str, Any] = {}
                if field is not None and selection.arguments:
                    changes["arguments"] = ast_sequence(
                        argument(item, field.args.get(item.name.value)) for item in selection.arguments
                    )
                if selection.selection_set is not None:
                    changes["selection_set"] = selection_set(
                        selection.selection_set, graphql.get_named_type(field.type) if field is not None else None
                    )
                selection = _replace(selection, **changes)
            elif isinstance(selection, graphql.InlineFragmentNode):
                condition = selection.type_condition
                on_type = schema.get_type(condition.name.value) if condition is not None else parent
                selection = _replace(selection, selection_set=selection_set(selection.selection_set, on_type))
            selections.append(selection)
        return _replace(node, selections=ast_sequence(selections))

    definitions: list[graphql.DefinitionNode] = []
    for definition in document.definitions:
        if isinstance(definition, graphql.OperationDefinitionNode):
            variable_definitions = list(definition.variable_definitions or ())
            shared.clear()
            root = getattr(schema, f"{definition.operation.value}_type")
            definition = _replace(
                definition,
                selection_set=selection_set(definition.selection_set, root),
                variable_definitions=ast_sequence(variable_definitions),
            )
        definitions.append(definition)
    return _replace(document, definitions=ast_sequence(definitions)), variables


def _replace(node: N, **changes: Any) -> N:
    return type(node)(**{**{key: getattr(node, key) for key in node.keys}, **changes})


def _is_inline_only(node: graphql.ValueNode) -> bool:
    # Variables and duplicate input fields have no JSON form
    if isinstance(node, graphql.ListValueNode):
        return any(map(_is_inline_only, node.values))
    if isinstance(node, graphql.ObjectValueNode):
        return len({field.name.value for field in node.fields}) != len(node.fields) or any(
            _is_inline_only(field.value) for field in node.fields
        )
    return isinstance(node, graphql.VariableNode)


def _coerces(value: Any, type_: graphql.GraphQLInputType) -> bool:
    # Invalid values raise in `graphql-core` < 3.3 and give `Undefined` in 3.3
    try:
        return graphql.coerce_input_value(value, type_) is not graphql.Undefined
    except graphql.GraphQLError:
        return False
