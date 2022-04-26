# pylint: disable=unused-import
import operator
from functools import wraps
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import attr
import graphql
from graphql import is_equal_type
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument
from hypothesis.strategies._internal.utils import cacheable

from .. import nodes
from ..types import AstPrinter, CustomScalars, Field, InputTypeNode, InterfaceOrObject, SelectionNodes
from . import factories, primitives
from .ast import make_mutation, make_query
from .containers import flatten
from .validation import maybe_parse_schema, validate_custom_scalars, validate_fields

BY_NAME = operator.attrgetter("name")


def instance_cache(key_func: Callable) -> Callable:
    def decorator(method: Callable) -> Callable:
        @wraps(method)
        def wrapped(self: "GraphQLStrategy", *args: Any, **kwargs: Any) -> st.SearchStrategy:
            key = key_func(*args, **kwargs)
            memo = self._cache.setdefault(method.__name__, {})
            cached = memo.get(key)
            if cached is not None:
                return cached
            result = method(self, *args, **kwargs)
            memo[key] = result
            return result

        return wrapped

    return decorator


@attr.s(slots=True)
class GraphQLStrategy:
    """Strategy for generating various GraphQL nodes."""

    schema: graphql.GraphQLSchema = attr.ib()
    custom_scalars: CustomScalars = attr.ib(factory=dict)
    # As the schema is assumed to be immutable, there are a few strategy caches possible for internal components
    # This is a per-method cache without limits as they are proportionate to the schema size
    _cache: Dict[str, Dict] = attr.ib(factory=dict)

    def values(self, type_: graphql.GraphQLInputType) -> st.SearchStrategy[InputTypeNode]:
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
            type_name = type_.name
            if type_name in self.custom_scalars:
                return primitives.maybe_null(self.custom_scalars[type_name], nullable)
            return primitives.scalar(type_name, nullable)
        if isinstance(type_, graphql.GraphQLEnumType):
            values = tuple(type_.values)
            return primitives.enum(values, nullable)
        # Types with children
        if isinstance(type_, graphql.GraphQLList):
            return self.lists(type_, nullable)
        if isinstance(type_, graphql.GraphQLInputObjectType):
            return self.objects(type_, nullable)
        raise TypeError(f"Type {type_.__class__.__name__} is not supported.")

    @instance_cache(lambda type_, nullable=True: (make_type_name(type_), nullable))
    def lists(self, type_: graphql.GraphQLList, nullable: bool = True) -> st.SearchStrategy[graphql.ListValueNode]:
        """Generate a `graphql.ListValueNode`."""
        strategy = st.lists(self.values(type_.of_type))
        return primitives.maybe_null(strategy.map(nodes.List), nullable)

    @instance_cache(lambda type_, nullable=True: (type_.name, nullable))
    def objects(
        self, type_: graphql.GraphQLInputObjectType, nullable: bool = True
    ) -> st.SearchStrategy[graphql.ObjectValueNode]:
        """Generate a `graphql.ObjectValueNode`."""
        fields = {name: field for name, field in type_.fields.items() if self.can_generate_field(field)}
        strategy = subset_of_fields(fields, force_required=True).flatmap(self.lists_of_object_fields)
        return primitives.maybe_null(strategy.map(nodes.Object), nullable)

    def can_generate_field(self, field: graphql.GraphQLInputField) -> bool:
        """Whether it is possible to generate values for the given field."""
        type_ = unwrap_field_type(field)
        return (
            # Can generate any non-scalar
            not isinstance(type_, graphql.GraphQLScalarType)
            # Default scalars
            or type_.name in {"Int", "Float", "String", "ID", "Boolean"}
            # User-provided scalars
            or type_.name in self.custom_scalars
        )

    def lists_of_object_fields(
        self, items: List[Tuple[str, Field]]
    ) -> st.SearchStrategy[List[graphql.ObjectFieldNode]]:
        return st.tuples(*(self.values(field.type).map(factories.object_field(name)) for name, field in items)).map(
            list
        )

    @instance_cache(lambda interface, implementations: (interface.name, tuple(impl.name for impl in implementations)))
    def interfaces(
        self, interface: graphql.GraphQLInterfaceType, implementations: List[InterfaceOrObject]
    ) -> st.SearchStrategy[SelectionNodes]:
        """Build query for GraphQL interface type."""
        # If there are implementations that have fields with the same name but different types
        # then the resulting query should not have these fields simultaneously
        strategies, overlapping_fields = self.collect_fragment_strategies(implementations)
        if overlapping_fields:
            return compose_interfaces_with_filter(self.selections(interface), strategies, self.schema.type_map)
        # No overlapping - safe to choose any subset of fields within the interface itself and any fragment
        return st.tuples(self.selections(interface), *strategies).map(flatten)  # type: ignore

    @instance_cache(lambda items: tuple(item.name for item in items))
    def inline_fragments(self, items: List[graphql.GraphQLObjectType]) -> st.SearchStrategy[SelectionNodes]:
        """Create inline fragment nodes for each given item."""
        # If there are implementations that have fields with the same name but different types
        # then the resulting query should not have these fields simultaneously
        strategies, overlapping_fields = self.collect_fragment_strategies(items)
        if overlapping_fields:
            return compose_interfaces_with_filter(st.just([]), strategies, self.schema.type_map)
        # No overlapping - safe to choose any subset of fields within the interface itself and any fragment
        return st.tuples(*(self.inline_fragment(type_) for type_ in items)).map(list)

    @instance_cache(lambda type_: type_.name)
    def inline_fragment(self, type_: graphql.GraphQLObjectType) -> st.SearchStrategy[graphql.InlineFragmentNode]:
        """Build `InlineFragmentNode` for the given type."""
        return self.selections(type_).map(factories.inline_fragment(type_.name))

    @instance_cache(lambda type_, fields=None: (type_.name, fields))
    def selections(
        self,
        object_type: InterfaceOrObject,
        fields: Optional[Tuple[str, ...]] = None,
    ) -> st.SearchStrategy[List[graphql.FieldNode]]:
        """Generate a subset of fields defined on the given type."""
        if fields:
            subset = {name: value for name, value in object_type.fields.items() if name in fields}
        else:
            subset = object_type.fields
        # minimum 1 field, an empty query is not valid
        return subset_of_fields(subset).flatmap(self.lists_of_fields)

    def lists_of_fields(self, items: List[Tuple[str, Field]]) -> st.SearchStrategy[List[graphql.FieldNode]]:
        return st.tuples(
            *(
                st.tuples(self.list_of_arguments(field.args), self.selections_for_type(field)).map(
                    factories.field(name)
                )
                for name, field in items
            )
        ).map(list)

    @instance_cache(lambda items: tuple(item.name for item in items))
    def collect_fragment_strategies(
        self, items: List[graphql.GraphQLObjectType]
    ) -> Tuple[List[st.SearchStrategy[graphql.InlineFragmentNode]], bool]:
        field_types: Dict[str, graphql.GraphQLType] = {}
        strategies = []
        has_overlapping_fields = False
        for item in items:
            if not has_overlapping_fields:
                for name, field in item.fields.items():
                    if name in field_types:
                        if not is_equal_type(field.type, field_types[name]):
                            # There are fields with the same names but different types
                            has_overlapping_fields = True
                    else:
                        field_types[name] = field.type
            strategies.append(self.inline_fragment(item))
        return strategies, has_overlapping_fields

    def list_of_arguments(
        self, arguments: Dict[str, graphql.GraphQLArgument]
    ) -> st.SearchStrategy[List[graphql.ArgumentNode]]:
        """Generate a list `graphql.ArgumentNode` for a field."""
        if not arguments:
            return st.just([])

        @st.composite  # type: ignore
        def inner(draw: Any) -> List[graphql.ArgumentNode]:
            args = []
            for name, argument in arguments.items():
                try:
                    argument_strategy = self.values(argument.type)
                except InvalidArgument:
                    if not isinstance(argument.type, graphql.GraphQLNonNull):
                        # If the type is nullable, then either generate `null` or skip it completely
                        if draw(st.booleans()):
                            args.append(graphql.ArgumentNode(name=graphql.NameNode(value=name), value=nodes.Null))
                        continue
                    raise
                args.append(draw(argument_strategy.map(factories.argument(name))))
            return args

        return inner()

    def selections_for_type(
        self,
        field: graphql.GraphQLField,
    ) -> st.SearchStrategy[Optional[SelectionNodes]]:
        """Extract proper type from the field and generate field nodes for this type."""
        field_type = unwrap_field_type(field)
        if isinstance(field_type, graphql.GraphQLObjectType):
            return self.selections(field_type)
        if isinstance(field_type, graphql.GraphQLInterfaceType):
            # Besides the fields on the interface type, it is possible to generate inline fragments on types that
            # implement this interface type
            implementations = self.schema.get_implementations(field_type).objects
            if not implementations:
                # Shortcut when there are no implementations - take fields from the interface itself
                return self.selections(field_type)
            return st.lists(st.sampled_from(implementations), min_size=1, unique_by=BY_NAME).flatmap(
                lambda impls: self.interfaces(field_type, impls)
            )
        if isinstance(field_type, graphql.GraphQLUnionType):
            # A union is a set of object types - take a subset of them and generate inline fragments
            return st.lists(st.sampled_from(field_type.types), min_size=1, unique_by=BY_NAME).flatmap(
                self.inline_fragments
            )
        # Other types don't have fields
        return st.none()


def check_nullable(type_: graphql.GraphQLInputType) -> Tuple[graphql.GraphQLInputType, bool]:
    """Get the wrapped type and detect if it is nullable."""
    nullable = True
    if isinstance(type_, graphql.GraphQLNonNull):
        type_ = type_.of_type
        nullable = False
    return type_, nullable


def unwrap_field_type(field: Field) -> graphql.GraphQLNamedType:
    """Get the underlying field type which is not wrapped."""
    type_ = field.type
    while isinstance(type_, graphql.GraphQLWrappingType):
        type_ = type_.of_type
    return type_


def make_type_name(type_: graphql.GraphQLType) -> str:
    """Create a name for a type."""
    name = ""
    while isinstance(type_, graphql.GraphQLWrappingType):
        name += type_.__class__.__name__.replace("GraphQL", "")
        type_ = type_.of_type
    return f"{name}{type_.name}"


@st.composite  # type: ignore
def compose_interfaces_with_filter(
    draw: Any,
    already_selected: st.SearchStrategy[List],
    strategies: List[st.SearchStrategy[SelectionNodes]],
    type_map: Dict[str, graphql.GraphQLType],
) -> SelectionNodes:
    selection_nodes = draw(already_selected)
    # Store what fields are already used and their corresponding types
    seen: Dict[str, graphql.GraphQLType] = {}

    def mark_seen(frag: graphql.InlineFragmentNode) -> None:
        # Add this fragment's fields to `seen`
        fragment_type = type_map[frag.type_condition.name.value]
        for selected in frag.selection_set.selections:
            seen.setdefault(selected.name.value, fragment_type.fields[selected.name.value].type)

    def add_alias(frag: graphql.InlineFragmentNode) -> graphql.InlineFragmentNode:
        # Add an alias for all fields that have the same name with already selected ones but a different type
        fragment_type = type_map[frag.type_condition.name.value]
        for selected in frag.selection_set.selections:
            field_name = selected.name.value
            if field_name in seen:
                field_type = fragment_type.fields[field_name].type
                if not is_equal_type(seen[field_name], field_type):
                    selected.alias = graphql.NameNode(value=f"{field_name}_{make_type_name(field_type)}")
        return frag

    for strategy in strategies:
        fragment = draw(strategy.map(add_alias))
        selection_nodes.append(fragment)
        mark_seen(fragment)
    return selection_nodes


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
            return subset_of_fields(optional).map(required.__add__)
        return st.just(required)
    # pairs are unique by field name
    return st.lists(st.sampled_from(field_pairs), min_size=1, unique_by=lambda x: x[0])


def _make_strategy(
    schema: graphql.GraphQLSchema,
    *,
    type_: graphql.GraphQLObjectType,
    fields: Optional[Iterable[str]] = None,
    custom_scalars: Optional[CustomScalars] = None,
) -> st.SearchStrategy[List[graphql.FieldNode]]:
    if fields is not None:
        fields = tuple(fields)
        validate_fields(fields, type_.fields)
    if custom_scalars:
        validate_custom_scalars(custom_scalars)
    return GraphQLStrategy(schema, custom_scalars or {}).selections(type_, fields=fields)


@cacheable  # type: ignore
def queries(
    schema: Union[str, graphql.GraphQLSchema],
    *,
    fields: Optional[Iterable[str]] = None,
    custom_scalars: Optional[CustomScalars] = None,
    print_ast: AstPrinter = graphql.print_ast,
) -> st.SearchStrategy[str]:
    """A strategy for generating valid queries for the given GraphQL schema.

    The output query will contain a subset of fields defined in the `Query` type.

    :param schema: GraphQL schema as a string or `graphql.GraphQLSchema`.
    :param fields: Restrict generated fields to ones in this list.
    :param custom_scalars: Strategies for generating custom scalars.
    :param print_ast: A function to convert the generated AST to a string.
    """
    parsed_schema = maybe_parse_schema(schema)
    if parsed_schema.query_type is None:
        raise ValueError("Query type is not defined in the schema")
    return (
        _make_strategy(parsed_schema, type_=parsed_schema.query_type, fields=fields, custom_scalars=custom_scalars)
        .map(make_query)
        .map(print_ast)
    )


@cacheable  # type: ignore
def mutations(
    schema: Union[str, graphql.GraphQLSchema],
    *,
    fields: Optional[Iterable[str]] = None,
    custom_scalars: Optional[CustomScalars] = None,
    print_ast: AstPrinter = graphql.print_ast,
) -> st.SearchStrategy[str]:
    """A strategy for generating valid mutations for the given GraphQL schema.

    The output mutation will contain a subset of fields defined in the `Mutation` type.

    :param schema: GraphQL schema as a string or `graphql.GraphQLSchema`.
    :param fields: Restrict generated fields to ones in this list.
    :param custom_scalars: Strategies for generating custom scalars.
    :param print_ast: A function to convert the generated AST to a string.
    """
    parsed_schema = maybe_parse_schema(schema)
    if parsed_schema.mutation_type is None:
        raise ValueError("Mutation type is not defined in the schema")
    return (
        _make_strategy(parsed_schema, type_=parsed_schema.mutation_type, fields=fields, custom_scalars=custom_scalars)
        .map(make_mutation)
        .map(print_ast)
    )
