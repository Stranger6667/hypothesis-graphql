from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Tuple, TypeVar, Union

import graphql
from hypothesis import strategies as st

from ..types import Field, InputTypeNode, InterfaceOrObject, SelectionNodes
from . import primitives
from .context import Context


def selections(
    context: Context,
    object_type: InterfaceOrObject,
    fields: Optional[Tuple[str, ...]] = None,
) -> st.SearchStrategy[SelectionNodes]:
    """Generate a subset of fields defined on the given type."""
    if fields:
        subset = {name: value for name, value in object_type.fields.items() if name in fields}
    else:
        subset = object_type.fields
    # minimum 1 field, an empty query is not valid
    return subset_of_fields(subset).flatmap(lambda f: list_of_nodes(context, f, strategy=field_nodes))


def unwrap_field_type(field: Field) -> graphql.GraphQLNamedType:
    """Get the underlying field type which is not wrapped."""
    type_ = field.type
    while isinstance(type_, graphql.GraphQLWrappingType):
        type_ = type_.of_type
    return type_


def field_nodes(context: Context, name: str, field: graphql.GraphQLField) -> st.SearchStrategy[graphql.FieldNode]:
    """Generate a single field node with optional children."""
    return st.tuples(list_of_arguments(context, field.args), selections_for_type(context, field),).map(
        lambda tup: graphql.FieldNode(
            name=graphql.NameNode(value=name),
            arguments=tup[0],
            selection_set=graphql.SelectionSetNode(kind="selection_set", selections=tup[1]),
        )
    )


def selections_for_type(
    context: Context,
    field: graphql.GraphQLField,
) -> st.SearchStrategy[Optional[SelectionNodes]]:
    """Extract proper type from the field and generate field nodes for this type."""
    field_type = unwrap_field_type(field)
    if isinstance(field_type, graphql.GraphQLObjectType):
        return selections(context, field_type)
    if isinstance(field_type, graphql.GraphQLInterfaceType):
        # Besides the fields on the interface type, it is possible to generate inline fragments on types that
        # implement this interface type
        implementations = context.schema.get_implementations(field_type).objects
        if not implementations:
            # Shortcut when there are no implementations - take fields from the interface itself
            return selections(context, field_type)
        variants: List[InterfaceOrObject] = [field_type, *implementations]
        return unique_by(variants, lambda v: v.name).flatmap(lambda t: interfaces(context, t))
    if isinstance(field_type, graphql.GraphQLUnionType):
        # A union is a set of object types - take a subset of them and generate inline fragments
        return unique_by(field_type.types, lambda m: m.name).flatmap(lambda m: inline_fragments(context, m))
    # Other types don't have fields
    return st.none()


def interfaces(context: Context, types: List[InterfaceOrObject]) -> st.SearchStrategy[SelectionNodes]:
    strategies = [
        inline_fragment(context, type_) if isinstance(type_, graphql.GraphQLObjectType) else selections(context, type_)
        for type_ in types
    ]
    return st.tuples(*strategies).map(flatten).map(list)  # type: ignore


T = TypeVar("T")


def flatten(items: Tuple[Union[T, List[T]], ...]) -> Generator[T, None, None]:
    for item in items:
        if isinstance(item, list):
            yield from item
        else:
            yield item


def inline_fragments(context: Context, items: List[graphql.GraphQLObjectType]) -> st.SearchStrategy[SelectionNodes]:
    """Create inline fragment nodes for each given item."""
    return fixed_lists((inline_fragment(context, type_) for type_ in items))


def inline_fragment(
    context: Context, type_: graphql.GraphQLObjectType
) -> st.SearchStrategy[graphql.InlineFragmentNode]:
    """Build `InlineFragmentNode` for the given type."""
    return selections(context, type_).map(
        lambda sel: graphql.InlineFragmentNode(
            type_condition=graphql.NamedTypeNode(
                name=graphql.NameNode(value=type_.name),
            ),
            selection_set=graphql.SelectionSetNode(kind="selection_set", selections=sel),
        )
    )


def list_of_arguments(
    context: Context, kwargs: Dict[str, graphql.GraphQLArgument]
) -> st.SearchStrategy[List[graphql.ArgumentNode]]:
    """Generate a list `graphql.ArgumentNode` for a field."""
    args = []
    for name, argument in kwargs.items():
        try:
            argument_strategy = argument_values(context, argument)
        except TypeError as exc:
            if not isinstance(argument.type, graphql.GraphQLNonNull):
                continue
            raise TypeError("Non-nullable custom scalar types are not supported as arguments") from exc
        args.append(
            argument_strategy.map(
                # Use `node_name` to prevent the lambda always using the last `name` value in this loop.
                # See pylint W0640 (cell-var-from-loop)
                lambda arg, node_name=name: graphql.ArgumentNode(name=graphql.NameNode(value=node_name), value=arg)
            )
        )
    return fixed_lists(args)


def fixed_lists(args: Iterable[st.SearchStrategy[T]]) -> st.SearchStrategy[List[T]]:
    return st.tuples(*args).map(list)


def unique_by(variants: List[T], key: Callable[[T], Any]) -> st.SearchStrategy[List[T]]:
    return st.lists(st.sampled_from(variants), min_size=1, unique_by=key)


def argument_values(context: Context, argument: graphql.GraphQLArgument) -> st.SearchStrategy[InputTypeNode]:
    """Value of `graphql.ArgumentNode`."""
    return value_nodes(context, argument.type)


def value_nodes(context: Context, type_: graphql.GraphQLInputType) -> st.SearchStrategy[InputTypeNode]:
    """Generate value nodes of a type, that corresponds to the input type.

    They correspond to all `GraphQLInputType` variants:
        - GraphQLScalarType -> ScalarValueNode
        - GraphQLEnumType -> EnumValueNode
        - GraphQLInputObjectType -> ObjectValueNode

    GraphQLWrappingType[T] is unwrapped:
        - GraphQLList -> ListValueNode[T]
        - GraphQLNonNull -> T (processed with nullable=False)
    """
    type_, nullable = check_nullable(type_)
    # Types without children
    if isinstance(type_, graphql.GraphQLScalarType):
        return primitives.scalar(type_, nullable)
    if isinstance(type_, graphql.GraphQLEnumType):
        return primitives.enum(type_, nullable)
    # Types with children
    if isinstance(type_, graphql.GraphQLList):
        return lists(context, type_, nullable)
    if isinstance(type_, graphql.GraphQLInputObjectType):
        return objects(context, type_, nullable)
    raise TypeError(f"Type {type_.__class__.__name__} is not supported.")


def check_nullable(type_: graphql.GraphQLInputType) -> Tuple[graphql.GraphQLInputType, bool]:
    """Get the wrapped type and detect if it is nullable."""
    nullable = True
    if isinstance(type_, graphql.GraphQLNonNull):
        type_ = type_.of_type
        nullable = False
    return type_, nullable


def lists(
    context: Context, type_: graphql.GraphQLList, nullable: bool = True
) -> st.SearchStrategy[graphql.ListValueNode]:
    """Generate a `graphql.ListValueNode`."""
    type_ = type_.of_type
    list_value = st.lists(value_nodes(context, type_))
    return primitives.maybe_null(list_value.map(lambda values: graphql.ListValueNode(values=values)), nullable)


def objects(
    context: Context, type_: graphql.GraphQLInputObjectType, nullable: bool = True
) -> st.SearchStrategy[graphql.ObjectValueNode]:
    """Generate a `graphql.ObjectValueNode`."""
    fields_value = subset_of_fields(type_.fields, force_required=True).flatmap(
        lambda fields: list_of_nodes(context, fields, strategy=object_field_nodes)
    )
    return primitives.maybe_null(fields_value.map(lambda fields: graphql.ObjectValueNode(fields=fields)), nullable)


def subset_of_fields(
    fields: Dict[str, Field], *, force_required: bool = False
) -> st.SearchStrategy[List[Tuple[str, Field]]]:
    """A helper to select a subset of fields."""
    field_pairs = sorted(fields.items())
    # if we need to always generate required fields, then return them and extend with a subset of optional fields
    if force_required:
        required, optional = [], {}
        for name, field in field_pairs:
            # TYPING: `field` is always `GraphQLInputField` as `force_required` equals `True` only with
            # `GraphQLInputObjectType`. A better solution is to create a separate function
            if graphql.is_required_input_field(field):  # type: ignore
                required.append((name, field))
            else:
                optional[name] = field
        if optional:
            return subset_of_fields(optional).map(lambda p: p + required)
        return st.just(required)
    # pairs are unique by field name
    return st.lists(st.sampled_from(field_pairs), min_size=1, unique_by=lambda x: x[0])


def object_field_nodes(
    context: Context, name: str, field: graphql.GraphQLInputField
) -> st.SearchStrategy[graphql.ObjectFieldNode]:
    return value_nodes(context, field.type).map(
        lambda value: graphql.ObjectFieldNode(name=graphql.NameNode(value=name), value=value)
    )


def list_of_nodes(
    context: Context,
    items: List[Tuple],
    strategy: Callable[[Context, str, Field], st.SearchStrategy],
) -> st.SearchStrategy[List]:
    return fixed_lists((strategy(context, name, field) for name, field in items))
