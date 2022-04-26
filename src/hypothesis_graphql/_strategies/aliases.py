from typing import Dict, List, Optional, Tuple

import graphql

from ..types import SelectionNodes


def maybe_add_alias_to_node(node: graphql.SelectionNode, seen: Dict[Tuple[str, str], List]) -> None:
    if isinstance(node, graphql.FieldNode):
        maybe_add_alias(node, node.arguments, seen)
        if node.selection_set.selections:
            for selection in node.selection_set.selections:
                maybe_add_alias_to_node(selection, seen)
    if isinstance(node, graphql.InlineFragmentNode):
        for selection in node.selection_set.selections:
            maybe_add_alias(selection, selection.arguments, seen)
            if selection.selection_set.selections:
                for sub_selection in selection.selection_set.selections:
                    maybe_add_alias_to_node(sub_selection, seen)


def maybe_add_alias(
    field_node: graphql.FieldNode, arguments: List[graphql.ArgumentNode], seen: Dict[Tuple[str, str], List]
) -> None:
    for argument in arguments:
        key = (field_node.name.value, argument.name.value)
        value = argument.value
        if key in seen:
            # Simply add an alias, the values could be the same, so it not technically necessary, but this is safe
            # and simpler, but a bit reduces the possible input variety
            field_node.alias = graphql.NameNode(value=f"{field_node.name.value}_{len(seen[key])}")
            seen[key].append(value)
        else:
            seen[key] = [value]


def add_selection_aliases(nodes: Optional[SelectionNodes]) -> Optional[SelectionNodes]:
    """Add aliases to fields that have conflicting argument types."""
    if nodes and len(nodes) > 1:
        seen: Dict[Tuple[str, str], List] = {}
        for node in nodes:
            maybe_add_alias_to_node(node, seen)
    return nodes
